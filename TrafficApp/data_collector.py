import requests
import datetime
import pandas as pd
import time
from django.conf import settings

API_KEY = settings.GOOGLE_CLIENT_SECRET

ROUTES = [
    ("Mile 17 Buea", "Malingo Junction Buea"),
    ("Malingo Junction Buea", "Great Soppo Buea"),
    ("Great Soppo Buea", "Check Point Buea"),
]

def get_route_data(origin, destination):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"

    params = {
        "origins": origin,
        "destinations": destination,
        "departure_time": "now",
        "key": API_KEY
    }

    res = requests.get(url, params=params).json()

    element = res['rows'][0]['elements'][0]

    distance_km = element['distance']['value'] / 1000
    duration = element['duration']['value'] / 60
    duration_traffic = element['duration_in_traffic']['value'] / 60

    now = datetime.datetime.now()

    # Compute speed
    speed = distance_km / (duration_traffic / 60)

    # Compute congestion
    ratio = duration_traffic / duration

    if ratio < 1.2:
        congestion = "Low"
    elif ratio < 1.5:
        congestion = "Medium"
    else:
        congestion = "High"

    return {
        "route": f"{origin}-{destination}",
        "distance": round(distance_km, 2),
        "hour": now.hour,
        "day": now.strftime("%A"),
        "travel_time": round(duration_traffic, 2),
        "speed": round(speed, 2),
        "congestion": congestion
    }

def collect_data():
    all_data = []

    for origin, destination in ROUTES:
        try:
            data = get_route_data(origin, destination)
            all_data.append(data)
            print("Collected:", data)
        except Exception as e:
            print("Error:", e)

    df = pd.DataFrame(all_data)

    df.to_csv("google_traffic_data.csv", mode='a', header=False, index=False)

if __name__ == "__main__":
    while True:
        collect_data()
        time.sleep(1800)  # every 30 minutes