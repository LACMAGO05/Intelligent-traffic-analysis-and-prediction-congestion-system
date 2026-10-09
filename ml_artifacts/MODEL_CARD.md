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
- **Training-data provenance is unverified:** the training run did not record an input-file fingerprint. The available `traffic_training_export.csv` matches this schema's cleaned row count (12,890), binary class totals (12,222 Free-flow / 668 Congested), and 68-route vocabulary, but it cannot be confirmed as the exact input. That export spans 2026-05-07 through 2026-06-05 and contains 15 original `High` rows; these observations conflict with the previous ~15-day / 8-`High` note and should not be attributed to this model's exact training set.
- SHA-256 of the available comparison export `traffic_training_export.csv`: `4387d1d9b829d77e37933df284fafe02d05ab8e0f4dd3d45ca6a46b320efb1ca` (comparison fingerprint only; not a recorded training-input fingerprint).
- Route one-hots are sparse; unseen routes serve as all-zero (model relies on time/weather/context).
- 'High' congestion in the UI is surfaced by Google's live duration_in_traffic, not this model.
