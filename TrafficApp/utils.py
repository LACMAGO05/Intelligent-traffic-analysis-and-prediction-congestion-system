import random
import requests
from django.conf import settings

def generate_otp():
    return str(random.randint(100000, 999999))

def get_realtime_traffic(origin, destination, departure_time="now"):
    """
    Fetches traffic data from Google Distance Matrix API.
    Can be for 'now' or a specific timestamp.
    """
    api_key = getattr(settings, 'GOOGLE_CLIENT_SECRET', None)
    if not api_key:
        return {"error": "Google API Key not configured"}

    # Ensure regional context (Buea, Cameroon) to avoid ambiguity with other cities
    def clean_loc(loc):
        loc = loc.strip()
        if "buea" not in loc.lower():
            return f"{loc}, Buea, Cameroon"
        return loc

    origin_clean = clean_loc(origin)
    dest_clean = clean_loc(destination)

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin_clean,
        "destinations": dest_clean,
        "departure_time": departure_time,
        "key": api_key
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()

        if data['status'] != 'OK':
            return {"error": f"API Error: {data['status']}"}

        element = data['rows'][0]['elements'][0]
        if element['status'] != 'OK':
            return {"error": f"Route Error: {element['status']}"}

        distance_km = element['distance']['value'] / 1000
        duration_min = element['duration']['value'] / 60
        duration_traffic_min = element.get('duration_in_traffic', element['duration'])['value'] / 60

        # Compute speed (km/h)
        speed = distance_km / (duration_traffic_min / 60) if duration_traffic_min > 0 else 0

        # Compute congestion level
        ratio = duration_traffic_min / duration_min if duration_min > 0 else 1
        if ratio < 1.2:
            congestion = "Low"
        elif ratio < 1.5:
            congestion = "Medium"
        else:
            congestion = "High"

        import datetime
        if isinstance(departure_time, int):
            dt = datetime.datetime.fromtimestamp(departure_time)
        else:
            dt = datetime.datetime.now()

        return {
            "route": f"{origin}-{destination}",
            "distance": round(distance_km, 2),
            "hour": dt.hour,
            "day": dt.strftime("%A"),
            "travel_time": round(duration_traffic_min, 2),
            "speed": round(speed, 2),
            "congestion": congestion,
            "status": "success",
            "is_prediction": departure_time != "now"
        }
    except Exception as e:
        return {"error": str(e)}
