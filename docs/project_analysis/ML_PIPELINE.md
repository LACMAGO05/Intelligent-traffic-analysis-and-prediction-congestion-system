# TrafficPro — Machine Learning Pipeline

> **Status:** Understanding-only. No production code or model artifacts were modified.
> **Generated:** 2026-05-30
> **Scope:** Training, artifacts, runtime inference, feature engineering, and the hybrid fusion logic.

## 1. Purpose

The ML pipeline produces a **congestion classification** (Low / Medium / High) with class probabilities and a confidence score for a given route + time + context. Critically, this model output is **not** the final answer shown to users — it is one input to the `HybridPredictionService`, which fuses it with Google Maps live data and expert rules to produce the "Smart ETA".

## 2. Pipeline Stages

```
[COLLECTION]                  [TRAINING - offline]            [INFERENCE - runtime]
traffic_collector/  ──CSV──>  Model_training.ipynb  ──pkl──>  ModelService.predict()
google_traffic_data_v2.csv    feature build + fit             feature vector → probs
                              label encoding                   → argmax → label
       ▲                                                              │
       │ (also written by predict_view, 7-col schema)                 ▼
       └─────────────────────────────────────────────  HybridPredictionService._apply_hybrid_logic()
```

The loop is **file-mediated and manual**: collector writes CSV → a human runs the notebook → artifacts are committed → `ModelService` loads them. There is no automated/online retraining.

## 3. Artifacts

| File | Size | Role |
|---|---|---|
| `traffic_model.pkl` | ~1.0 MB | **Loaded at runtime** by `ModelService` (`joblib.load`) |
| `model_XGBoost.pkl` | ~734 KB | XGBoost model (pickle) |
| `traffic_xgb_model.json` | ~837 KB | XGBoost booster (JSON export) |
| `label_encoder.pkl` | ~495 B | Maps class indices ↔ Low/Medium/High |
| `google_traffic_data_v2.csv` | ~1.4 MB | Training + log data |

> **Naming/format drift (risk):** code and docstrings refer to a **"LightGBM"** model, but the artifacts are **XGBoost**, and the file actually loaded is `traffic_model.pkl` (not obviously either named file). Which artifact is canonical is ambiguous.

## 4. Runtime Inference — `ModelService` ([model_service.py](../../TrafficApp/services/model_service.py))

```
__init__:
  model   = joblib.load(BASE_DIR/'traffic_model.pkl')      # per instantiation
  encoder = joblib.load(BASE_DIR/'label_encoder.pkl')
  feature_names = [22 fixed columns]   # must match training order

predict(features_dict):
  1. pd.DataFrame([features_dict])
  2. one-hot expand categoricals:
       route → {Malingo to UB Junction, Mile 17 to Malingo, UB Junction to Check Point}
       weather_condition → {Clouds, Drizzle, Rain, Thunderstorm}
       rainfall_status → {Rain}
       event_type → {Market Activity}
  3. derived: is_weekend (day>=5), is_morning_rush (7<=hour<=9),
              prev_hour_speed default 20.0
  4. X = df.reindex(columns=feature_names, fill_value=0)   # order + fill missing
  5. probs = model.predict(X)[0]; class_idx = argmax(probs)
  6. label = encoder.inverse_transform([class_idx])
  7. → {congestion_level, probabilities{label:pct}, confidence, status}
```

**Feature schema (`feature_names`, 22 cols):** `distance_km, hour, day_of_week, holiday_indicator, school_holiday_indicator, school_hours_indicator, working_hours_indicator, office_rush_hour_indicator, event_indicator, event_severity, is_weekend, is_morning_rush, prev_hour_speed` + 3 one-hot route cols + 4 weather one-hots + `rainfall_status_Rain` + `event_type_Market Activity`.

## 5. Feature Engineering

- **Inference-time features** are assembled in `HybridPredictionService._prepare_ml_features()` from Google route data + the context bundle, then expanded inside `ModelService.predict()`.
- **Collector-time features** (`traffic_collector/feature_engineering.py`) add cyclical hour (sin/cos), weekend, peak-hour, and rush-hour weight — **but** `collector.py` calls `add_ml_features` only via a commented-out line, so these are not currently persisted.
- `prev_hour_speed` is a real training feature but at inference is **hardcoded to 20.0** (no lookup of the actual previous hour), which weakens any temporal signal the model learned.

## 6. Hybrid Fusion — `_apply_hybrid_logic()`

The model's congestion class and confidence feed a rules engine that adjusts Google's duration:

```
base = Google traffic_duration; google_congestion = classify(normal, traffic)
delay_adjustment = 0
  A. model=High & google!=High & confidence>65   → +25% of normal_duration
  B. rainfall=Rain                                → +5.5 (if google Low) else +3.0
  C. school rush (not school holiday)             → +4.0
  D. office rush                                  → +5.0
  E. pressure<20 & google!=Low                    → -2.0
final_smart_eta = max(google+delay, normal_duration)
pressure_score (0–100) → risk level + stability
→ XAI: adjustment_reasons[], ai_reasoning[], smart_recommendation
```

Outputs include `travel_time` (= smart ETA), `congestion` (= **model** class), `confidence_score`, `probabilities`, `traffic_pressure_score`, `pressure_level/trend`, `context_analysis`, `risk_analysis`, `polyline`, `segments_delay`.

## 7. Interactions & Dependencies

- **Upstream:** Google Directions (route metrics), context providers (weather/holiday/school/event), CSV training data.
- **Libraries:** pandas (unpinned), `numpy`, `joblib`, XGBoost — the latter three are **not in `requirements.txt`**, a deployment risk.
- **Downstream:** `predict_view` → JSON → frontend card.

## 8. Risks

1. **Train/serve skew:** `prev_hour_speed` defaulted to 20.0 at serve time; `is_weekend`/`is_morning_rush` recomputed in two places; cyclical-hour features trained-but-not-served (or vice versa) depending on the notebook. Any mismatch silently degrades accuracy.
2. **Route coverage gap:** model encodes only **3 routes** as one-hots; the collector polls **~60** route pairs. Unknown routes collapse to all-zero one-hots (`fill_value=0`), so most production routes get no route-specific signal.
3. **Model/format/naming drift** (XGBoost vs "LightGBM", which `.pkl` is canonical).
4. **Missing dependencies** for inference (`numpy`/`joblib`/xgboost unpinned) — works locally, may fail on a clean deploy.
5. **No model versioning/validation/monitoring** — artifacts are loose files with no schema check, metrics gate, or drift detection. A bad retrain ships silently.
6. **Dual-schema CSV pollution:** `predict_view` appends 7-col rows while `CSVManager` writes 20-col rows to the same file; the training notebook must reconcile or risk corrupt features.
7. **Confidence/probabilities depend on encoder class order** — `prob_map` is built by zipping `encoder.classes_`, correct only if the encoder matches the model's class indexing.

## 9. Scalability Concerns

- **Per-request model load:** `joblib.load` runs on every prediction (new `ModelService` per request). At scale this dominates latency and memory; a process-cached singleton or model server is needed.
- **CSV as the data lake:** appends + last-100-line dedupe scan are not concurrency-safe and grow O(file); training data on ephemeral PaaS disk can be lost on restart.
- **Manual retraining loop:** no scheduled/automated pipeline; model staleness grows with time and the human-in-the-loop cadence.
- **No feature store / caching of context** means inference recomputes (and re-fetches) context every call.
- **Single model, single region** — scaling to more cities/routes requires re-encoding routes and retraining; the 3-route one-hot design does not generalize.
