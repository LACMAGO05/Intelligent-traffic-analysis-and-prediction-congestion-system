"""
Reproducible, gated training for the congestion model.

    python manage.py train_model --csv google_traffic_data_v2.csv --promote

Pipeline: clean -> binary target (Congested vs Free-flow) -> all-route one-hot
-> chronological split -> class-weighted LightGBM -> per-class metrics + gate.

The new model is only promoted when it passes the gate (minority-class recall
and ROC-AUC thresholds). Promotion publishes a complete versioned release and
atomically switches the active manifest; prior releases remain available for
rollback. Otherwise the candidate is kept for inspection.
"""
import os
import hashlib
import tempfile
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand

from traffic_context import ml_features as mlf
from TrafficApp.services.artifact_manifest import promote_artifact_release


def _read_training_csv(path):
    """Parse and fingerprint one captured byte stream with bounded memory use."""
    digest = hashlib.sha256()
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as captured:
        with open(path, "rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                captured.write(chunk)
        captured.seek(0)
        frame = pd.read_csv(captured, on_bad_lines="skip", engine="python")
    return frame, digest.hexdigest()


class Command(BaseCommand):
    help = "Clean the dataset, train the binary congestion model, validate, and (optionally) promote it."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default=str(settings.BASE_DIR / "google_traffic_data_v2.csv"))
        parser.add_argument("--test-frac", type=float, default=0.2, help="Chronological holdout fraction.")
        parser.add_argument("--min-recall", type=float, default=0.30,
                            help="Gate: minimum recall on the Congested class.")
        parser.add_argument("--min-auc", type=float, default=0.60, help="Gate: minimum ROC-AUC.")
        parser.add_argument("--promote", action="store_true",
                            help="Overwrite the live artifact if the gate passes.")

    def handle(self, *args, **opts):
        import lightgbm as lgb
        from sklearn.metrics import (
            average_precision_score, classification_report, confusion_matrix,
            precision_recall_curve, roc_auc_score,
        )

        artifacts_dir = settings.BASE_DIR / "ml_artifacts"
        candidate_dir = artifacts_dir / "candidate"
        for d in (artifacts_dir, candidate_dir):
            os.makedirs(d, exist_ok=True)

        # ── load + clean ──────────────────────────────────────────────
        raw, input_sha256 = _read_training_csv(opts["csv"])
        df = mlf.clean_training_frame(raw)
        df["_ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["_ts"]).sort_values("_ts")
        self.stdout.write(f"Loaded {len(raw)} rows -> {len(df)} clean rows.")

        route_vocab = sorted(df["route"].astype(str).unique().tolist())
        X = mlf.build_feature_frame(df, route_vocab)
        y = mlf.binary_target(df["congestion"]).to_numpy()
        self.stdout.write(
            f"Target balance: Free-flow={int((y == 0).sum())}  Congested={int((y == 1).sum())} "
            f"| routes={len(route_vocab)} | features={X.shape[1]}"
        )
        if y.sum() == 0 or y.sum() == len(y):
            self.stderr.write(self.style.ERROR("Only one class present after cleaning; aborting."))
            return

        # ── chronological split (no future leakage) ───────────────────
        split = int(len(X) * (1 - opts["test_frac"]))
        X_train, X_test = X.iloc[:split], X.iloc[split:]
        y_train, y_test = y[:split], y[split:]

        pos = max(int(y_train.sum()), 1)
        neg = int((y_train == 0).sum())
        scale_pos_weight = neg / pos  # counteract imbalance

        model = lgb.LGBMClassifier(
            objective="binary",
            n_estimators=400,
            learning_rate=0.05,
            num_leaves=31,
            scale_pos_weight=scale_pos_weight,
            random_state=42,
            verbose=-1,
        )
        model.fit(X_train, y_train)

        def _roc(yt, p):
            try:
                return float(roc_auc_score(yt, p)) if len(set(yt)) > 1 else float("nan")
            except ValueError:
                return float("nan")

        def _pr(yt, p):  # PR-AUC (average precision) — the honest metric for a rare class
            try:
                return float(average_precision_score(yt, p)) if len(set(yt)) > 1 else float("nan")
            except ValueError:
                return float("nan")

        # ── tune the decision threshold on TRAINING data ───────────────
        # Tuning on the test set would leak; with this little data, training is
        # the pragmatic, honest choice (note: mildly optimistic).
        train_proba = model.predict_proba(X_train)[:, 1]
        prec_t, rec_t, thr_t = precision_recall_curve(y_train, train_proba)
        f1_t = 2 * prec_t * rec_t / (prec_t + rec_t + 1e-12)
        threshold = float(thr_t[int(np.nanargmax(f1_t[:-1]))]) if len(thr_t) else 0.5

        # ── evaluate on the chronological holdout ──────────────────────
        proba = model.predict_proba(X_test)[:, 1]
        y_pred = (proba >= threshold).astype(int)

        auc = _roc(y_test, proba)
        pr_auc = _pr(y_test, proba)
        report = classification_report(
            y_test, y_pred, labels=[0, 1],
            target_names=["Free-flow", "Congested"], zero_division=0, output_dict=True,
        )
        cm = confusion_matrix(y_test, y_pred, labels=[0, 1])
        congested_recall = report["Congested"]["recall"]

        # ── dumb baseline: route × hour average congestion rate ────────
        # If LightGBM can't beat this lookup table, the ML adds nothing.
        base = df.iloc[:split].copy()
        base["_y"] = y_train
        lookup = base.groupby(["route", "hour"])["_y"].mean()
        global_rate = float(y_train.mean())
        base_proba = df.iloc[split:].apply(
            lambda r: lookup.get((r["route"], r["hour"]), global_rate), axis=1
        ).to_numpy()
        base_pr_auc = _pr(y_test, base_proba)
        base_roc = _roc(y_test, base_proba)

        self.stdout.write("\n=== Holdout evaluation (chronological 20%) ===")
        self.stdout.write(classification_report(
            y_test, y_pred, labels=[0, 1],
            target_names=["Free-flow", "Congested"], zero_division=0))
        self.stdout.write(f"Confusion matrix [rows=true, cols=pred] (Free-flow, Congested):\n{cm}")
        self.stdout.write(f"Tuned threshold (from train PR curve): {threshold:.3f}")
        self.stdout.write(
            f"MODEL    -> PR-AUC: {pr_auc:.3f} | ROC-AUC: {auc:.3f} | Congested recall: {congested_recall:.3f}")
        self.stdout.write(
            f"BASELINE -> PR-AUC: {base_pr_auc:.3f} | ROC-AUC: {base_roc:.3f}  (route × hour lookup)")
        beats = pr_auc > base_pr_auc
        self.stdout.write((self.style.SUCCESS if beats else self.style.WARNING)(
            f"PR-AUC verdict: model {'beats' if beats else 'does NOT beat'} the baseline."))

        metrics = {
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "input_file": os.path.basename(opts["csv"]),
            "input_sha256": input_sha256,
            "input_date_start": df["_ts"].min().isoformat(),
            "input_date_end": df["_ts"].max().isoformat(),
            "original_high_rows": int(df["congestion"].eq("High").sum()),
            "rows_clean": int(len(df)), "n_features": int(X.shape[1]),
            "free_flow": int((y == 0).sum()), "congested": int((y == 1).sum()),
            "roc_auc": auc, "pr_auc": pr_auc,
            "baseline_pr_auc": base_pr_auc, "baseline_roc_auc": base_roc,
            "threshold": threshold,
            "congested_recall": congested_recall,
            "congested_precision": report["Congested"]["precision"],
            "congested_f1": report["Congested"]["f1-score"],
        }

        # ── gate ──────────────────────────────────────────────────────
        passed = (not np.isnan(auc)) and auc >= opts["min_auc"] and congested_recall >= opts["min_recall"]
        version = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")

        import joblib
        cand_model = candidate_dir / "traffic_model.pkl"
        cand_schema = candidate_dir / "feature_schema.json"
        joblib.dump(model.booster_, cand_model)
        mlf.save_schema(cand_schema, route_vocab, threshold=threshold, metrics=metrics, version=version)
        self.stdout.write(f"\nCandidate written to {candidate_dir}")

        if not passed:
            self.stdout.write(self.style.WARNING(
                f"GATE FAILED (need AUC>={opts['min_auc']} and Congested recall>={opts['min_recall']}). "
                f"Not promoting. Candidate kept for inspection."))
            return

        self.stdout.write(self.style.SUCCESS("GATE PASSED."))
        if not opts["promote"]:
            self.stdout.write("Re-run with --promote to overwrite the live model.")
            return

        release_dir = promote_artifact_release(
            settings.BASE_DIR, cand_model, cand_schema, version
        )
        self._write_model_card(artifacts_dir / "MODEL_CARD.md", metrics, route_vocab, version)
        self.stdout.write(self.style.SUCCESS(f"Promoted model {version} -> {release_dir}."))

    def _write_model_card(self, path, metrics, route_vocab, version):
        with open(path, "w") as fh:
            fh.write(
                f"# Model Card — Traffic Congestion Classifier\n\n"
                f"- **Version:** {version}\n"
                f"- **Algorithm:** LightGBM (binary classification) — active release selected by `ml_artifacts/current.json`\n"
                f"- **Target:** Congested (orig. Medium/High) vs Free-flow (orig. Low)\n"
                f"- **Trained:** {metrics['trained_at']}\n\n"
                f"## Data\n"
                f"- Clean rows: {metrics['rows_clean']} | Free-flow: {metrics['free_flow']} | Congested: {metrics['congested']}\n"
                f"- Routes encoded: {len(route_vocab)} | Features: {metrics['n_features']}\n\n"
                f"## Training input\n"
                f"- File: `{metrics['input_file']}`\n"
                f"- SHA-256: `{metrics['input_sha256']}`\n"
                f"- Cleaned timestamp range: {metrics['input_date_start']} to {metrics['input_date_end']}\n"
                f"- Original `High` rows: {metrics['original_high_rows']}\n"
                f"- The fingerprint identifies the input bytes used for this run; it does not independently establish the dataset's upstream provenance.\n\n"
                f"## Holdout metrics (chronological 20%)\n"
                f"- PR-AUC (honest headline): {metrics.get('pr_auc', float('nan')):.3f} "
                f"vs route×hour baseline {metrics.get('baseline_pr_auc', float('nan')):.3f}\n"
                f"- ROC-AUC: {metrics['roc_auc']:.3f} (flattered by class imbalance)\n"
                f"- Decision threshold (tuned on train): {metrics.get('threshold', 0.5):.3f}\n"
                f"- Congested precision/recall/F1: "
                f"{metrics['congested_precision']:.3f} / {metrics['congested_recall']:.3f} / {metrics['congested_f1']:.3f}\n\n"
                f"## Known limitations\n"
                f"- Route one-hots are sparse; unseen routes serve as all-zero (model relies on time/weather/context).\n"
                f"- 'High' congestion in the UI is surfaced by Google's live duration_in_traffic, not this model.\n"
            )
