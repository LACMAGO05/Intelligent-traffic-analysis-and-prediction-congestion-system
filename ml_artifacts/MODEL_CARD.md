# Model Card — Traffic Congestion Classifier

- **Version:** 20260608-024821
- **Algorithm:** LightGBM (binary classification) — canonical artifact `traffic_model.pkl`
- **Target:** Congested (orig. Medium/High) vs Free-flow (orig. Low)
- **Trained:** 2026-06-08T02:48:21.405321+00:00

## Data
- Clean rows: 12890 | Free-flow: 12222 | Congested: 668
- Routes encoded: 68 | Features: 86

## Holdout metrics (chronological 20%)
- PR-AUC (honest headline): 0.540 vs route×hour baseline 0.327
- ROC-AUC: 0.872 (flattered by class imbalance)
- Decision threshold (tuned on train): 0.941
- Congested precision/recall/F1: 0.742 / 0.298 / 0.425

## Known limitations
- Collected over a ~15-day window; only 8 original 'High' samples (hence binary framing).
- Route one-hots are sparse; unseen routes serve as all-zero (model relies on time/weather/context).
- 'High' congestion in the UI is surfaced by Google's live duration_in_traffic, not this model.
