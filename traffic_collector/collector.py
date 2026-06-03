import time
from datetime import datetime
from django.conf import settings
from django.db import close_old_connections
from traffic_context.logger import logger
from traffic_context.weather_service import WeatherService
from traffic_context.holiday_service import HolidayService
from traffic_context.school_service import SchoolService
from traffic_context.event_detector import EventDetector
from traffic_context.congestion import CongestionIntelligence
from traffic_context.pressure_score import PressureScoreCalculator
from traffic_context.feature_engineering import FeatureEngineer
from traffic_context.directions_client import DirectionsClient, DirectionsError, parse_leg_metrics
from .record_store import TrafficRecordStore

class TrafficCollector:
    def __init__(self):
        self.weather_service = WeatherService()
        self.holiday_service = HolidayService()
        self.school_service = SchoolService()
        self.event_detector = EventDetector()
        self.record_store = TrafficRecordStore()
        self.pressure_calculator = PressureScoreCalculator()
        self.directions = DirectionsClient(timeout=15)
        self.api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        self.routes = getattr(settings, 'TRAFFIC_ROUTES', [])

    def collect_all_routes(self):
        logger.info("Starting collection for all routes...")

        # This runs in a long-lived background (APScheduler) thread; drop any
        # stale/timed-out DB connections before doing ORM work this cycle.
        close_old_connections()

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

        # Persist to the durable database store
        success = self.record_store.append_record(record)
        if success:
            logger.info(f"Successfully recorded traffic for {origin} to {destination}")

    def fetch_google_traffic(self, origin, destination):
        try:
            _, _, data = self.directions.fetch(origin, destination, departure_time="now")
        except DirectionsError as e:
            return {"error": str(e)}

        try:
            leg = data['routes'][0]['legs'][0]
            distance_km, duration_min, duration_traffic_min = parse_leg_metrics(leg)

            speed = distance_km / (duration_traffic_min / 60) if duration_traffic_min > 0 else 0
            congestion = CongestionIntelligence.classify(duration_min, duration_traffic_min)

            return {
                "distance_km": round(distance_km, 2),
                "travel_time_mins": round(duration_traffic_min, 2),
                "speed_kmh": round(speed, 2),
                "congestion": congestion
            }
        except Exception as e:
            return {"error": str(e)}
