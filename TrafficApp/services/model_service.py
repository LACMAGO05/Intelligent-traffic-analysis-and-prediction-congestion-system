import joblib
import pandas as pd
import numpy as np
import os
import logging
from functools import lru_cache
from django.conf import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_artifacts():
    """
    Load the model + label encoder exactly once per process.

    Previously a fresh ~1 MB model was loaded from disk on every prediction
    (a new ModelService per request). Caching here removes that per-request I/O.
    NOTE: because the artifacts are cached for the life of the process, a
    retrained model requires a process restart (or ``_load_artifacts.cache_clear()``)
    to take effect.
    """
    model_path = os.path.join(settings.BASE_DIR, 'traffic_model.pkl')
    encoder_path = os.path.join(settings.BASE_DIR, 'label_encoder.pkl')

    model = None
    if os.path.exists(model_path):
        try:
            model = joblib.load(model_path)
        except Exception as exc:
            logger.error("Error loading model: %s", exc)

    encoder = None
    if os.path.exists(encoder_path):
        try:
            encoder = joblib.load(encoder_path)
        except Exception as exc:
            logger.error("Error loading encoder: %s", exc)

    return model, encoder


class ModelService:
    """
    Service responsible for loading the LightGBM model and label encoders,
    preprocessing features, and running predictions.
    """

    def __init__(self):
        # Model and encoder are loaded once per process and reused (see above).
        self.model, self.encoder = _load_artifacts()

        # Define the exact feature names the model expects (must match training)
        # Based on Model_training.ipynb and csv columns
        self.feature_names = [
            'distance_km', 'hour', 'day_of_week',
            'holiday_indicator', 'school_holiday_indicator', 'school_hours_indicator',
            'working_hours_indicator', 'office_rush_hour_indicator', 'event_indicator',
            'event_severity', 'is_weekend', 'is_morning_rush', 'prev_hour_speed',
            'route_Malingo to UB Junction', 'route_Mile 17 to Malingo', 'route_UB Junction to Check Point',
            'weather_condition_Clouds', 'weather_condition_Drizzle', 'weather_condition_Rain', 'weather_condition_Thunderstorm',
            'rainfall_status_Rain', 'event_type_Market Activity'
        ]

    def predict(self, features_dict):
        """
        Processes features and returns congestion probabilities.

        Parameters:
            features_dict (dict): Dictionary containing all required features

        Returns:
            dict: Prediction results including level, probabilities, and confidence
        """
        if not self.model:
            return {"error": "Model not loaded"}

        # Prepare input for the model
        try:
            # 1. Create a DataFrame from the input features
            df_input = pd.DataFrame([features_dict])

            # 2. Re-create dummy columns for categorical features
            # Note: We must ensure all columns expected by the model are present
            cat_cols = {
                'route': ['Malingo to UB Junction', 'Mile 17 to Malingo', 'UB Junction to Check Point'],
                'weather_condition': ['Clouds', 'Drizzle', 'Rain', 'Thunderstorm'],
                'rainfall_status': ['Rain'],
                'event_type': ['Market Activity']
            }

            for col, values in cat_cols.items():
                val = features_dict.get(col)
                for possible_val in values:
                    col_name = f"{col}_{possible_val}"
                    df_input[col_name] = 1 if val == possible_val else 0

            # 3. Add derived features (matching training logic)
            df_input['is_weekend'] = 1 if features_dict.get('day_of_week', 0) >= 5 else 0
            hour = features_dict.get('hour', 0)
            df_input['is_morning_rush'] = 1 if 7 <= hour <= 9 else 0

            # Use distance as a proxy for prev_hour_speed if not available
            if 'prev_hour_speed' not in df_input.columns:
                 df_input['prev_hour_speed'] = 20.0 # Default speed

            # 4. Ensure correct order and presence of all features
            X = df_input.reindex(columns=self.feature_names, fill_value=0)

            # 5. Run prediction
            # LightGBM returns an array of probabilities for each class [Low, Medium, High]
            probs = self.model.predict(X)[0]
            class_idx = np.argmax(probs)

            # 6. Decode the predicted class
            prediction_label = "Low" # Fallback
            if self.encoder:
                prediction_label = self.encoder.inverse_transform([class_idx])[0]

            # Map probabilities to labels
            prob_map = {}
            if self.encoder:
                for idx, label in enumerate(self.encoder.classes_):
                    prob_map[label] = round(float(probs[idx]) * 100, 1)
            else:
                prob_map = {"Low": round(probs[0]*100, 1), "Medium": round(probs[1]*100, 1), "High": round(probs[2]*100, 1)}

            return {
                "congestion_level": prediction_label,
                "probabilities": prob_map,
                "confidence": round(float(np.max(probs)) * 100, 1),
                "status": "success"
            }

        except Exception as e:
            return {"error": f"Prediction error: {str(e)}"}
