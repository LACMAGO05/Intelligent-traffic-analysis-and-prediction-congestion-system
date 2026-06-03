"""
Single source of truth for the model's feature engineering.

Both the training command (``manage.py train_model``) and the serving layer
(``TrafficApp.services.model_service``) build features through the functions
here, so the model is never fed a different feature space than it was trained on
(the H6 train/serve skew that previously made every live prediction error out).

Design notes:
* The target is **binary**: 1 = Congested (original Medium/High), 0 = Free-flow
  (original Low). The raw data has only 8 "High" rows, so a 3-class model can't
  learn it; Google's live ``duration_in_traffic`` still surfaces "High" at serve.
* ``prev_hour_speed`` is intentionally NOT a feature: it cannot be reproduced at
  serve time (no per-route history lookup), so training on it caused skew.
* ``speed_kmh`` / ``travel_time_mins`` are excluded — congestion is derived from
  them, so they would be target leakage.
* The exact ordered column list + the route vocabulary are persisted to
  ``feature_schema.json`` so serving reconstructs identical columns.
"""
import json
import re

import pandas as pd


def _safe(name):
    """Sanitise a string for use as a LightGBM feature name (no spaces/JSON chars)."""
    return re.sub(r"[^0-9A-Za-z]+", "_", str(name)).strip("_")


def route_col(route):
    """Deterministic, LightGBM-safe column name for a route."""
    return f"route_{_safe(route)}"

# Order matters and must match between training and serving.
BASE_NUMERIC = ["distance_km", "hour", "day_of_week", "is_weekend", "is_morning_rush"]
INDICATORS = [
    "holiday_indicator", "school_holiday_indicator", "school_hours_indicator",
    "working_hours_indicator", "office_rush_hour_indicator", "event_indicator",
    "event_severity",
]
WEATHER_CATEGORIES = ["Clouds", "Rain", "Drizzle", "Thunderstorm", "Clear"]

TARGET_MAP = {0: "Free-flow", 1: "Congested"}
SEVERITY_MAP = {"Low": 0, "Medium": 1, "High": 2}
CONGESTED_LABELS = {"Medium", "High"}


def to_severity(value):
    """Map an event-severity label (or pre-encoded int) to 0/1/2."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    return SEVERITY_MAP.get(str(value), 0)


def feature_columns(route_vocab):
    """The exact ordered feature columns for a given route vocabulary."""
    cols = list(BASE_NUMERIC) + list(INDICATORS)
    cols += [f"weather_{w}" for w in WEATHER_CATEGORIES]
    cols += ["rainfall_Rain"]
    cols += [route_col(r) for r in route_vocab]
    return cols


def row_to_features(rec, route_vocab):
    """Build the feature dict for a single record (used by training and serving)."""
    try:
        hour = int(rec.get("hour", 0) or 0)
    except (ValueError, TypeError):
        hour = 0
    try:
        dow = int(rec.get("day_of_week", 0) or 0)
    except (ValueError, TypeError):
        dow = 0

    def _int(key):
        try:
            return int(rec.get(key, 0) or 0)
        except (ValueError, TypeError):
            return 0

    feat = {
        "distance_km": float(rec.get("distance_km", 0) or 0),
        "hour": hour,
        "day_of_week": dow,
        "is_weekend": 1 if dow >= 5 else 0,
        "is_morning_rush": 1 if 7 <= hour <= 9 else 0,
        "holiday_indicator": _int("holiday_indicator"),
        "school_holiday_indicator": _int("school_holiday_indicator"),
        "school_hours_indicator": _int("school_hours_indicator"),
        "working_hours_indicator": _int("working_hours_indicator"),
        "office_rush_hour_indicator": _int("office_rush_hour_indicator"),
        "event_indicator": _int("event_indicator"),
        "event_severity": to_severity(rec.get("event_severity", 0)),
    }

    weather = str(rec.get("weather_condition", "Clouds") or "Clouds")
    for w in WEATHER_CATEGORIES:
        feat[f"weather_{w}"] = 1 if weather == w else 0

    rainfall = str(rec.get("rainfall_status", "No Rain") or "No Rain")
    feat["rainfall_Rain"] = 1 if rainfall == "Rain" else 0

    route = str(rec.get("route", "") or "")
    for r in route_vocab:
        feat[route_col(r)] = 1 if route == r else 0

    return feat


def build_feature_frame(df, route_vocab):
    """Vectorised feature matrix for a cleaned DataFrame, in canonical column order."""
    cols = feature_columns(route_vocab)
    records = [row_to_features(rec, route_vocab) for rec in df.to_dict("records")]
    return pd.DataFrame(records, columns=cols).fillna(0)


def clean_training_frame(df):
    """
    Repair the collected CSV before training.

    Drops the column-shifted/ragged rows (the H5 corruption: weekday strings in
    `hour`, floats in `day`), coerces numerics, normalises weather, and keeps only
    valid congestion labels.
    """
    df = df.copy()

    df["hour"] = pd.to_numeric(df["hour"], errors="coerce")
    df["day_of_week"] = pd.to_numeric(df["day_of_week"], errors="coerce")
    df["distance_km"] = pd.to_numeric(df["distance_km"], errors="coerce")
    df = df.dropna(subset=["hour", "day_of_week", "distance_km", "congestion", "route"])
    df = df[(df["hour"].between(0, 23)) & (df["day_of_week"].between(0, 6))]
    df = df[df["congestion"].isin(["Low", "Medium", "High"])]

    for col in ["holiday_indicator", "school_holiday_indicator", "school_hours_indicator",
                "working_hours_indicator", "office_rush_hour_indicator", "event_indicator"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["event_severity"] = df["event_severity"].map(to_severity)

    df["weather_condition"] = df["weather_condition"].fillna("Clouds").replace({"Error": "Clouds"})
    df["rainfall_status"] = df["rainfall_status"].fillna("No Rain").replace({"Unknown": "No Rain"})
    return df


def binary_target(congestion_series):
    """1 = Congested (Medium/High), 0 = Free-flow (Low)."""
    return congestion_series.isin(CONGESTED_LABELS).astype(int)


# ── schema persistence ────────────────────────────────────────────────────────

def save_schema(path, route_vocab, threshold=0.5, metrics=None, version=None):
    payload = {
        "version": version,
        "model_type": "lightgbm-binary",
        "target": TARGET_MAP,
        "threshold": threshold,
        "weather_categories": WEATHER_CATEGORIES,
        "route_vocab": list(route_vocab),
        "feature_columns": feature_columns(route_vocab),
        "metrics": metrics or {},
    }
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2)
    return payload


def load_schema(path):
    with open(path) as fh:
        return json.load(fh)
