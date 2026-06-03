# Model Card — Traffic Congestion Classifier

- **Version:** 20260531-031815
- **Algorithm:** LightGBM (binary classification) — canonical artifact `traffic_model.pkl`
- **Target:** Congested (orig. Medium/High) vs Free-flow (orig. Low)
- **Trained:** 2026-05-31T03:18:15.209494+00:00

## Data
- Clean rows: 11722 | Free-flow: 11167 | Congested: 555
- Routes encoded: 68 | Features: 86

## Holdout metrics (chronological 20%)
- ROC-AUC: 0.915
- Congested precision/recall/F1: 0.564 / 0.629 / 0.595

## Known limitations
- Collected over a ~15-day window; only 8 original 'High' samples (hence binary framing).
- Route one-hots are sparse; unseen routes serve as all-zero (model relies on time/weather/context).
- 'High' congestion in the UI is surfaced by Google's live duration_in_traffic, not this model.
