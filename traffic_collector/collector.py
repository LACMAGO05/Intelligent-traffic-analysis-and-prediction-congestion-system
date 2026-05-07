import requests
import time
from datetime import datetime
from django.conf import settings
from .logger import logger
from .weather_service import WeatherService
from .holiday_service import HolidayService
from .school_service import SchoolService
from .event_detector import EventDetector
from .csv_manager import CSVManager
from .congestion import CongestionIntelligence
from .pressure_score import PressureScoreCalculator
from .feature_engineering import FeatureEngineer

class TrafficCollector:
    def __init__(self):
        self.weather_service = WeatherService()
        self.holiday_service = HolidayService()
        self.school_service = SchoolService()
        self.event_detector = EventDetector()
        self.csv_manager = CSVManager()
        self.pressure_calculator = PressureScoreCalculator()
        self.api_key = getattr(settings, 'GOOGLE_CLIENT_SECRET', None)
        self.routes = getattr(settings, 'TRAFFIC_ROUTES', [])

    def collect_all_routes(self):
        logger.info("Starting collection for all routes...")
        
        # Get common contextual data once per collection cycle
        now = datetime.now()
        weather_data = self.weather_service.get_current_weather()
        is_holiday = self.holiday_service.is_public_holiday(now.date())
        school_indicators = self.school_service.get_indicators(now)
        event_info = self.event_detector.get_event_info(now)
        office_indicators = self.event_detector.get_office_indicators(now)
        
        context = {
            **weather_data,
            "holiday_indicator": is_holiday,
            **school_indicators,
            **event_info,
            **office_indicators,
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "hour": now.hour,
            "day": now.strftime("%A"),
            "day_of_week": now.weekday()
        }

        for origin, destination in self.routes:
            try:
                self.collect_route_data(origin, destination, context)
                # Sleep briefly to avoid hitting rate limits too fast
                time.sleep(1)
            except Exception as e:
                logger.error(f"Failed to collect data for route {origin} to {destination}: {e}")

    def collect_route_data(self, origin, destination, context):
        traffic_data = self.fetch_google_traffic(origin, destination)
        
        if "error" in traffic_data:
            logger.error(f"Google API Error for {origin}-{destination}: {traffic_data['error']}")
            return

        # Combine with context
        record = {**context, **traffic_data}
        record["route"] = f"{origin} to {destination}"
        
        # Calculate Pressure Score
        record["traffic_pressure_score"] = self.pressure_calculator.calculate(record)
        
        # Add ML features (optional but good for future)
        # record = FeatureEngineer.add_ml_features(record)
        
        # Save to CSV
        success = self.csv_manager.append_record(record)
        if success:
            logger.info(f"Successfully recorded traffic for {origin} to {destination}")

    def fetch_google_traffic(self, origin, destination):
        if not self.api_key:
            return {"error": "API Key missing"}

        def clean_loc(loc):
            loc = loc.strip()
            if "buea" not in loc.lower():
                return f"{loc}, Buea, Cameroon"
            return loc

        url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            "origin": clean_loc(origin),
            "destination": clean_loc(destination),
            "departure_time": "now",
            "traffic_model": "best_guess",
            "key": self.api_key
        }

        try:
            response = requests.get(url, params=params, timeout=15)
            data = response.json()

            if data['status'] != 'OK':
                return {"error": f"API Status: {data['status']}"}

            leg = data['routes'][0]['legs'][0]
            
            duration_km = leg['distance']['value'] / 1000
            duration_min = leg['duration']['value'] / 60
            duration_traffic_min = leg.get('duration_in_traffic', leg['duration'])['value'] / 60
            
            speed = duration_km / (duration_traffic_min / 60) if duration_traffic_min > 0 else 0
            congestion = CongestionIntelligence.classify(duration_min, duration_traffic_min)

            return {
                "distance_km": round(duration_km, 2),
                "travel_time_mins": round(duration_traffic_min, 2),
                "speed_kmh": round(speed, 2),
                "congestion": congestion
            }
        except Exception as e:
            return {"error": str(e)}
