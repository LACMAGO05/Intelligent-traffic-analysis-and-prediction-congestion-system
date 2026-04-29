
import os
import joblib
import re
import traceback
from django.conf import settings


try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except Exception:
    nlp = None

__all__ = ['predict_traffic', 'extract_from_text', 'encoders']

BASE_DIR = settings.BASE_DIR

# ── Load saved model files ────────────────────────────────────────────
model     = joblib.load(os.path.join(BASE_DIR, 'TrafficApp', 'best_traffic_model.pkl'))
encoders  = joblib.load(os.path.join(BASE_DIR, 'TrafficApp', 'label_encoders.pkl'))
label_map = joblib.load(os.path.join(BASE_DIR, 'TrafficApp', 'traffic_label_map.pkl'))


# ROAD EXTRACTION — with fuzzy fallback

def extract_road(text_lower):
    """
    Tries to find a road name in the user's message.

    Strategy:
      1. Exact substring match (e.g. 'mile 17' in text)
      2. Partial / fuzzy match (e.g. 'malingo' matches 'Malingo Junction')
      3. Fallback to first road in the encoder rather than crashing
    """
    roads_list = list(encoders['Roads'].classes_)

    # 1. Exact match
    for r in roads_list:
        if r.lower() in text_lower:
            return r

    # 2. Partial match — check if any word in the road name appears in text
    #    e.g. user types "malingo" → matches "Malingo Junction"
    for r in roads_list:
        road_words = r.lower().split()
        for word in road_words:
            if len(word) >= 4 and word in text_lower:  # skip short words like 'at', 'of'
                return r

    # 3. Fallback — return first road instead of raising an error
    #    This prevents the whole request from crashing
    return roads_list[0]


# DAY EXTRACTION

def extract_day(text_lower):
    """
    Finds a day name in the user's message.
    Returns 'Monday' as default if no day is found.
    """
    days = ["monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday"]
    for d in days:
        if d in text_lower:
            return d.capitalize()
    return "Monday"  # safe default



# TIME EXTRACTION  ← THIS IS WHERE THE MAIN BUG WAS

def extract_time(text_lower):
    """
    Extracts the hour (0-23) from the user's message.

    Priority order:
      1. Keyword: morning / afternoon / evening / night
      2. Explicit time with am/pm: '8am', '6 pm', '10am'
            ← OLD BUG: regex r'(\d+)(am|pm)?' also matched road numbers like '17'
            ← FIX:     regex r'\b(\d{1,2})\s*(am|pm)\b' REQUIRES am/pm suffix
      3. Bare number with no am/pm (least reliable, used as last resort)
      4. Default: 8 (morning rush)
    """
    # 1. Keyword-based time (most reliable — user says "morning" etc.)
    if "morning" in text_lower:
        return 8
    if "afternoon" in text_lower:
        return 14
    if "evening" in text_lower:
        return 18
    if "night" in text_lower:
        return 20
    if "midnight" in text_lower:
        return 0
    if "noon" in text_lower:
        return 12

    # 2. Explicit am/pm time  ← FIXED REGEX
    # \b    = word boundary (prevents matching mid-word)
    # \d{1,2} = 1 or 2 digit number (1-12 for hours)
    # \s*   = optional space between number and am/pm
    # (am|pm) = REQUIRED — this is what prevents matching road numbers
    # \b    = word boundary at the end
    match = re.search(r'\b(\d{1,2})\s*(am|pm)\b', text_lower)
    if match:
        hour   = int(match.group(1))
        period = match.group(2)
        if period == 'pm' and hour != 12:
            hour += 12   # 6pm → 18
        if period == 'am' and hour == 12:
            hour = 0     # 12am → 0 (midnight)
        return hour

    # 3. Last resort: bare number between 1-23 with no am/pm
    #    Only used if user types something like "I travel at 8"
    #    Skips numbers >= 24 which are likely road numbers (Mile 17, Mile 16)
    match = re.search(r'\bat\s+(\d{1,2})\b', text_lower)
    if match:
        hour = int(match.group(1))
        if 1 <= hour <= 23:
            return hour

    # 4. Default
    return 8


# MAIN EXTRACTION FUNCTION
def extract_from_text(text):
    """
    Extracts road, hour, and day from a natural language message.

    Examples that now work correctly:
      "I'm going to Mile 17 on Monday at 8am"   → ('Mile 17', 8, 'Monday')
      "Checkpoint friday evening"                → ('Checkpoint', 18, 'Friday')
      "malingo junction tuesday morning"         → ('Malingo Junction', 8, 'Tuesday')
      "Great Soppo 6pm wednesday"               → ('Great Soppo', 18, 'Wednesday')

    Parameters:
        text (str): raw user message from the chat input

    Returns:
        tuple: (road: str, hour: int, day: str)
    """
    text_lower = text.lower().strip()

    road = extract_road(text_lower)
    day  = extract_day(text_lower)
    hour = extract_time(text_lower)

    return road, hour, day


# TIME SLOT CONVERSION
def get_peak_range(hour):
    """
    Converts a raw hour (0-23) into the time slot format
    that the model was trained on.
    """
    if   6  <= hour < 8:  return "6am-8am"
    elif 8  <= hour < 10: return "8am-10am"
    elif 10 <= hour < 12: return "10am-12pm"
    elif 12 <= hour < 16: return "12pm-4pm"
    elif 16 <= hour < 18: return "4pm-6pm"
    elif 18 <= hour < 20: return "6pm-8pm"
    elif 20 <= hour < 22: return "8pm-10pm"
    else:                  return "8am-10am"   # midnight/early hours → default



# DELAY ESTIMATE
def estimate_delay(label):
    delays = {
        "Low":    "0–5 mins",
        "Medium": "10–15 mins",
        "High":   "20–30+ mins",
    }
    return delays.get(label, "Unknown")


# PREDICTION FUNCTION

def predict_traffic(road, hour, day):
    """
    Predicts traffic congestion level given road, hour, and day.

    Parameters:
        road (str): e.g. 'Mile 17'
        hour (int): e.g. 8  (24-hour format)
        day  (str): e.g. 'Monday'

    Returns:
        dict: {
            'label':      'Low' | 'Medium' | 'High',
            'confidence': float (0-100),
            'delay':      str
        }
    """
    peak = get_peak_range(hour)

    # Encode each input using saved LabelEncoders
    # If a value is unseen, fall back to 0 safely
    road_enc = (
        encoders['Roads'].transform([road])[0]
        if road in encoders['Roads'].classes_
        else 0
    )
    peak_enc = (
        encoders['Peak hours'].transform([peak])[0]
        if peak in encoders['Peak hours'].classes_
        else 0
    )
    day_enc = (
        encoders['Day'].transform([day])[0]
        if day in encoders['Day'].classes_
        else 0
    )

    features   = [[road_enc, peak_enc, day_enc]]
    prediction = model.predict(features)[0]
    proba      = model.predict_proba(features)[0]
    confidence = round(float(max(proba)) * 100, 2)

    # int() converts numpy int64 to plain Python int for dict lookup
    label = label_map[int(prediction)]

    return {
        "label":      label,
        "confidence": confidence,
        "delay":      estimate_delay(label),
    }
