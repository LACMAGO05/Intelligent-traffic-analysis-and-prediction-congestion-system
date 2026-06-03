# Phase 5 — AI & ML Improvements (Changelog)

**Date:** 2026-05-31
**Audit items:** H6 (train/serve skew + route encoding), ML-note (validation/versioning), L1 (naming/model card).
**Validation:** `manage.py check` clean · **41/41 tests pass** · model trained, gated, promoted · **live hybrid prediction now uses the model** (no fallback).

---

## 🔴 Root-cause found first

`model_service.predict()` was returning `{'error': 'train and valid dataset categorical_feature do not match.'}` on **every** call. The deployed LightGBM model expected **81 features** (63 underscore-named route one-hots + a `day` categorical + `prev_hour_speed`), but serving reindexed to **22** space-named features. The hybrid layer's `model_pred.get('congestion_level', google_congestion)` silently swallowed the error and fell back to Google's classification — so **the ML model had never actually run in the app.** Phase 5 makes it run, train/serve-aligned and validated.

## Decision: binary target

Data is 11,167 Low / 547 Medium / **8 High** — a 3-class model can't learn "High". Per your decision, the target is **binary: Congested (Medium+High) vs Free-flow (Low)**, trained with class weights. "High" is still shown to users, surfaced from Google's live `duration_in_traffic`.

## 5.1 — Single source of truth for features *(H6)*

New **`traffic_context/ml_features.py`** used by both training and serving:
- `clean_training_frame()` — drops the column-shifted/ragged rows (weekday strings in `hour`, etc.), coerces types, normalises weather ("Error"/"Unknown" → defaults).
- `row_to_features()` / `build_feature_frame()` / `feature_columns()` — deterministic, LightGBM-safe feature names.
- `binary_target()`, schema `save_schema`/`load_schema`.
- **Removed skew sources:** dropped `prev_hour_speed` (unreproducible at serve), dropped the `day` categorical (caused the serving crash), excluded `speed_kmh`/`travel_time_mins` (target leakage — congestion is derived from them).

## 5.2 — Expanded route encoding + retrain *(H6)*

`manage.py train_model` encodes **all 68 routes** present after cleaning (vs the old 3), persisted in `feature_schema.json`. Serving builds the route string as `"{origin} to {destination}"` to match the training vocabulary; unknown routes degrade to all-zeros (model relies on time/weather/context).

## 5.3 — Reproducible training + validation gate *(ML-note)*

New **`TrafficApp/management/commands/train_model.py`**:
- Chronological split (no future leakage), class-weighted (`scale_pos_weight`) LightGBM.
- Reports per-class precision/recall/F1, confusion matrix, ROC-AUC.
- **Gate:** promotes only if `ROC-AUC ≥ 0.60` **and** Congested recall `≥ 0.30` (configurable). Otherwise writes to `ml_artifacts/candidate/`.
- On promote: **backs up** the previous artifact to `ml_artifacts/backup/`, writes `traffic_model.pkl` + `feature_schema.json`, and a model card.

**Holdout metrics (chronological 20%):**

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Free-flow | 0.97 | 0.96 | 0.97 | 2170 |
| Congested | 0.56 | 0.63 | 0.59 | 175 |

**ROC-AUC 0.915** · Congested recall 0.63 (110/175 caught). Gate passed.

## 5.4 — Serving rewrite + model card + naming *(L1)*

- **`model_service.py`** rewritten: loads model + `feature_schema.json` (cached once/process), builds features via the shared module, returns a binary prediction mapped to the UI vocab (Congested→"Medium", Free-flow→"Low") with probabilities/confidence. Falls back cleanly to `{"error": ...}` (→ Google) if artifacts are missing.
- **Hybrid** (`hybrid_prediction_service.py`): displays `max(model_congestion, google_congestion)` so "High" from Google is never lost; Logic-A now fires when the model flags congestion Google underestimates.
- **Model card:** `ml_artifacts/MODEL_CARD.md` documents algorithm (canonical = **LightGBM** `traffic_model.pkl`), version, data, metrics, and limitations. This ends the "LightGBM vs XGBoost" confusion — `model_XGBoost.pkl` / `traffic_xgb_model.json` are **superseded** (kept for reference only).

## Files

| File | Change |
|---|---|
| `traffic_context/ml_features.py` | **new** — shared clean/feature/schema logic |
| `TrafficApp/management/commands/train_model.py` | **new** — gated, reproducible training |
| `TrafficApp/services/model_service.py` | rewritten to use the schema (fixes the crash) |
| `TrafficApp/services/hybrid_prediction_service.py` | route string + most-severe display + Logic A |
| `feature_schema.json`, `traffic_model.pkl`, `ml_artifacts/` | promoted model + schema + card + backup |
| `TrafficApp/tests.py` | +`MLFeatureTests`, `ModelServingTests`, `HybridDisplayTests`; fixed cache test |

## Risks / follow-ups

- **Deployment (Phase 6):** `traffic_model.pkl` is git-ignored — production must run `train_model --promote` (or ship the artifact) on deploy, else serving degrades to the Google fallback. `feature_schema.json` **is** tracked.
- **Retrain requires restart:** artifacts are cached per process (`_load_artifacts.cache_clear()` or restart to reload).
- **Data limitation:** ~15-day window, sparse per-route congestion — present as honest "future work" (collect longer, monitor drift). See [[dataset-findings]].
- `Model_training.ipynb` is superseded for training by `train_model` (keep for EDA).

## How to retrain

```bash
python manage.py train_model               # train + evaluate + gate (no promote)
python manage.py train_model --promote      # also overwrite the live model if gate passes
```
