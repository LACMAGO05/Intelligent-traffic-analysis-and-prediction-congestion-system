# Machine-learning pipeline

TrafficPro uses a binary LightGBM classifier as one input to its hybrid route prediction. The model classifies **Free-flow** versus **Congested** (originally Low versus Medium/High). It does not produce the UI’s High class; the hybrid layer can surface High from Google live traffic data.

## Data and training

The normal data path is:

1. The collector stores route observations and context in PostgreSQL `TrafficRecord` rows.
2. `python manage.py export_training_data` exports those records to a clean CSV. The default output is `traffic_training_export.csv`.
3. `python manage.py train_model --csv PATH` cleans the input, constructs the binary target and features, trains LightGBM, and evaluates a chronological holdout.

`train_model` defaults to a root `google_traffic_data_v2.csv` input path; that file may not exist in a checkout. Supply `--csv traffic_training_export.csv` (or another prepared dataset) when using the exported data. Dataset provenance and collection period should be documented with the data used for any new reported model result; the command does not itself establish provenance.

The shared feature logic is in `traffic_context/ml_features.py` and is used for both training and inference. It cleans malformed rows, encodes route identity, time/day, weekend and morning-rush indicators, school/holiday/office/event context, weather categories, and rainfall. `speed_kmh` and `travel_time_mins` are excluded from model features to avoid target leakage; `prev_hour_speed` is not used because it cannot be reconstructed by the current serving path.

Training sorts records by timestamp and uses a chronological holdout (default 20%). The congestion decision threshold is selected from training-set precision/recall values. Evaluation reports class metrics, ROC-AUC, PR-AUC, a confusion matrix, and a route-by-hour baseline. Promotion is gated by ROC-AUC and Congested recall (defaults: at least 0.60 and 0.30). Beating the baseline is reported but is not part of the promotion gate.

```bash
python manage.py train_model --csv traffic_training_export.csv
python manage.py train_model --csv traffic_training_export.csv --promote
```

The command writes candidate artifacts under `ml_artifacts/candidate/`. Each run records the SHA-256 of the exact input CSV, cleaned date range, and original High-label count in the candidate schema. That fingerprint identifies the bytes used for the run; it does not establish where the dataset originated. With `--promote`, if the configured gate passes, the command writes a complete versioned model/schema pair under `ml_artifacts/releases/<version>/` and atomically switches `ml_artifacts/current.json` to that release. The prior release remains available for rollback. It then regenerates `ml_artifacts/MODEL_CARD.md` from the run metadata. A gate pass without `--promote` does not replace the live model.

## Artifacts and serving

Serving first reads the release named by `ml_artifacts/current.json`:

- `ml_artifacts/releases/<version>/traffic_model.pkl` — serialized LightGBM Booster.
- `ml_artifacts/releases/<version>/feature_schema.json` — version, model type, target labels, decision threshold, ordered feature columns, route vocabulary, and training metrics.

The manifest pointer is replaced atomically only after both release files are complete. The loader verifies that the schema version matches the manifest. If no manifest exists, it falls back to the checked-in root `traffic_model.pkl` and `feature_schema.json` for backward compatibility. `TrafficApp.services.model_service.ModelService` loads the artifacts once per process. It builds features using the saved schema and maps the model’s binary output to Low or Medium. A missing or invalid artifact produces a model error; the hybrid service then falls back to Google’s congestion class. The model is cached, so replacing it requires restarting the process (or explicitly clearing the loader cache).

The checked-in legacy root schema identifies version `20260608-024821` and carries the metrics summarized in [MODEL_CARD.md](../ml_artifacts/MODEL_CARD.md). The older `docs/project_analysis/PHASE5_CHANGELOG.md` reports results from a different run; those figures should not be represented as metrics for this schema version. Repository presence of the artifacts does not by itself confirm that a deployed service receives both files.

## Limits and interpretation

- The current target is binary, so the model does not distinguish Medium from High.
- The model card notes the limited collection window and sparse congestion observations. Its metrics describe that version and split, not a guarantee of future performance.
- A route absent from the saved vocabulary has no route-specific one-hot feature; other available features remain.
- Google Maps is still required for live route metrics and the UI’s High classification. Model output is combined with Google and context rules; it is not a standalone travel-time guarantee.

See [MODEL_CARD.md](../ml_artifacts/MODEL_CARD.md) for the versioned summary, and [DATABASE.md](DATABASE.md) for the collection and export tables.
