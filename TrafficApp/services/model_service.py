import joblib
import logging
import os
from functools import lru_cache

import pandas as pd
from django.conf import settings

from traffic_context import ml_features as mlf
from .artifact_manifest import resolve_artifact_paths

logger = logging.getLogger(__name__)

# Binary target -> UI congestion vocabulary. "High" is never produced by the
# model (binary); it is surfaced from Google's live duration_in_traffic in the
# hybrid layer.
_UI_LABEL = {"Congested": "Medium", "Free-flow": "Low"}


@lru_cache(maxsize=1)
def _load_artifacts():
    """
    Load the LightGBM model + its feature schema exactly once per process.

    The schema in the manifest-selected release pins the ordered feature columns
    and route vocabulary. Legacy root artifacts are used only when no manifest
    exists. A retrained model requires a process restart (or cache clearing).
    """
    try:
        model_path, schema_path, release_version = resolve_artifact_paths(settings.BASE_DIR)
    except Exception as exc:
        logger.error("Invalid model artifact manifest (%s)", type(exc).__name__)
        return None, None

    model = None
    if os.path.exists(model_path):
        try:
            model = joblib.load(model_path)
        except Exception as exc:
            logger.error("Error loading model: %s", exc)

    schema = None
    if os.path.exists(schema_path):
        try:
            schema = mlf.load_schema(schema_path)
            if release_version and schema.get("version") != release_version:
                raise ValueError("Schema version does not match the active release")
        except Exception as exc:
            logger.error("Error loading feature schema: %s", exc)
            schema = None

    return model, schema


class ModelService:
    """
    Loads the trained congestion model and runs predictions using the exact
    feature schema it was trained with (see traffic_context.ml_features).
    """

    def __init__(self):
        self.model, self.schema = _load_artifacts()

    def predict(self, features_dict):
        """
        Returns binary congestion prediction mapped to the UI vocabulary.

        Parameters:
            features_dict (dict): raw context/route features (see ml_features).

        Returns:
            dict with ``congestion_level`` ("Low"/"Medium"), probabilities,
            confidence, and the raw binary label — or ``{"error": ...}`` so the
            hybrid layer can fall back to Google's classification.
        """
        if not self.model or not self.schema:
            return {"error": "Model not loaded"}

        try:
            route_vocab = self.schema["route_vocab"]
            columns = self.schema["feature_columns"]
            threshold = self.schema.get("threshold", 0.5)

            feat = mlf.row_to_features(features_dict, route_vocab)
            X = pd.DataFrame([feat]).reindex(columns=columns, fill_value=0)

            # LightGBM Booster (binary) returns P(class=1 = Congested).
            proba = float(self.model.predict(X)[0])
            is_congested = proba >= threshold
            internal = "Congested" if is_congested else "Free-flow"
            ui_label = _UI_LABEL[internal]
            confidence = round((proba if is_congested else 1 - proba) * 100, 1)

            return {
                "congestion_level": ui_label,
                "probabilities": {
                    "Low": round((1 - proba) * 100, 1),
                    "Medium": round(proba * 100, 1),
                },
                "confidence": confidence,
                "binary_label": internal,
                "congested_probability": round(proba * 100, 1),
                "status": "success",
            }

        except Exception as e:
            return {"error": f"Prediction error: {str(e)}"}
