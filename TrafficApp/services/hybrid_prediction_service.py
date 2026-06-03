import logging
from datetime import datetime
from .google_maps_service import GoogleMapsService
from .model_service import ModelService

# Shared context providers (neutral package, also used by the collector)
from traffic_context.weather_service import WeatherService
from traffic_context.holiday_service import HolidayService
from traffic_context.school_service import SchoolService
from traffic_context.event_detector import EventDetector
from traffic_context.pressure_score import PressureScoreCalculator
from traffic_context.congestion import CongestionIntelligence
from traffic_context.feature_engineering import FeatureEngineer

logger = logging.getLogger(__name__)

class HybridPredictionService:
    """
    The orchestrator service that combines Google Maps data with LightGBM predictions
    and local context (weather, schools, holidays, events) to produce a smart prediction.
    """

    def __init__(self):
        self.google_maps = GoogleMapsService()
        self.model_service = ModelService()

        # Initialize collector services
        self.weather_svc = WeatherService()
        self.holiday_svc = HolidayService()
        self.school_svc = SchoolService()
        self.event_det = EventDetector()
        self.pressure_calc = PressureScoreCalculator()
        self.feat_eng = FeatureEngineer()

    def get_hybrid_prediction(self, origin, destination, departure_time_raw):
        """
        Main workflow for hybrid prediction.
        """
        # 1. Get data from Google Maps
        # Convert departure_time_raw to timestamp if it's not 'now'
        departure_time = departure_time_raw
        google_data = self.google_maps.get_route_details(origin, destination, departure_time)

        if "error" in google_data:
            return google_data

        # 2. Gather local context intelligence
        # Determine the target datetime for context enrichment
        if departure_time == "now":
            target_dt = datetime.now()
        else:
            target_dt = datetime.fromtimestamp(int(departure_time))

        context = self._gather_context(target_dt)

        # 3. Enrich route data with context
        primary_route = google_data['primary_route']
        # Build the route string in the same "Origin to Destination" form the model
        # was trained on, so the route one-hot can match the known vocabulary.
        route_name = f"{origin} to {destination}"
        features = self._prepare_ml_features(primary_route, context, target_dt, route_name)

        # 4. Get LightGBM model prediction
        model_prediction = self.model_service.predict(features)

        # 5. Smart Hybrid Logic: Combine Google + Model + Context
        final_prediction = self._apply_hybrid_logic(google_data, model_prediction, context)

        return final_prediction

    def _gather_context(self, dt):
        """Uses existing collector services to get environmental context."""
        weather = self.weather_svc.get_current_weather()
        holiday = self.holiday_svc.is_public_holiday(dt.date())
        school = self.school_svc.get_indicators(dt)
        events = self.event_det.get_event_info(dt)
        office = self.event_det.get_office_indicators(dt)

        context = {
            **weather,
            "holiday_indicator": holiday,
            **school,
            **events,
            **office,
            "day_of_week": dt.weekday(),
            "hour": dt.hour,
            "is_weekend": dt.weekday() >= 5
        }
        return context

    def _prepare_ml_features(self, route, context, dt, route_name=None):
        """Engineers features for the LightGBM model."""
        features = {
            "distance_km": route['distance'],
            "hour": context['hour'],
            "day_of_week": context['day_of_week'],
            "holiday_indicator": 1 if context['holiday_indicator'] else 0,
            "school_holiday_indicator": 1 if context['school_holiday_indicator'] else 0,
            "school_hours_indicator": 1 if context['school_hours_indicator'] else 0,
            "working_hours_indicator": 1 if context['working_hours_indicator'] else 0,
            "office_rush_hour_indicator": 1 if context['office_rush_hour_indicator'] else 0,
            "event_indicator": 1 if context['event_indicator'] else 0,
            "event_severity": 1 if context['event_severity'] == 'Medium' else (2 if context['event_severity'] == 'High' else 0),
            "weather_condition": context['weather_condition'],
            "rainfall_status": context['rainfall_status'],
            "route": route_name or route['summary']
        }
        # Add pressure score for internal analysis (though model might not use it directly if it wasn't in training)
        # Re-calculate congestion for pressure score input
        congestion_lvl = CongestionIntelligence.classify(route['normal_duration'], route['traffic_duration'])
        features['congestion'] = congestion_lvl
        features['traffic_pressure_score'] = self.pressure_calc.calculate(features)

        return features

    def _apply_hybrid_logic(self, google_data, model_pred, context):
        """
        Combines Google Maps data and Model prediction with expert logic.
        Implements Explainable AI (XAI) features.
        """
        primary = google_data['primary_route']

        # 1. Extract base values from Google
        google_duration = primary['traffic_duration']
        google_congestion = CongestionIntelligence.classify(primary['normal_duration'], google_duration)

        # 2. Extract model values
        model_congestion = model_pred.get('congestion_level', google_congestion)
        model_confidence = model_pred.get('confidence', 0)
        probabilities = model_pred.get('probabilities', {})

        # The model is binary (Low/Medium); "High" is surfaced from Google's live
        # traffic. Display the more severe of the two so High is never lost.
        _SEV = {"Low": 0, "Medium": 1, "High": 2}
        display_congestion = max(model_congestion, google_congestion, key=lambda c: _SEV.get(c, 0))

        # 3. Intelligent ETA Adjustment Layer
        # This is the "Smart ETA Adjustment Engine"
        adjusted_duration = google_duration
        delay_adjustment = 0
        adjustment_reasons = []

        # Logic A: Model flags congestion that Google currently underestimates
        if model_congestion in ("Medium", "High") and google_congestion == "Low" and model_confidence > 65:
            extra = (primary['normal_duration'] * 0.25)
            delay_adjustment += extra
            adjustment_reasons.append(f"AI Model detected high congestion patterns ({model_confidence}% confidence)")

        # Logic B: Rainfall context (often underestimated by global maps)
        if context.get('rainfall_status') == "Rain":
            extra = 5.5 if google_congestion == "Low" else 3.0
            delay_adjustment += extra
            adjustment_reasons.append("Rainfall detected: Local traffic slows down significantly")

        # Logic C: School Rush Hour
        if context.get('school_hours_indicator') and not context.get('school_holiday_indicator'):
            delay_adjustment += 4.0
            adjustment_reasons.append("School rush hour: Increased activity near educational zones")

        # Logic D: Office Rush
        if context.get('office_rush_hour_indicator'):
            delay_adjustment += 5.0
            adjustment_reasons.append("Office rush: Peak commuting hour detected")

        # Logic E: Low pressure stability (Slight reduction if everything is clear)
        # We only reduce if Google shows some traffic and our pressure is very low
        temp_features = {**context, "congestion": model_congestion}
        pressure_score = self.pressure_calc.calculate(temp_features)

        if pressure_score < 20 and google_congestion != "Low":
            reduction = -2.0
            delay_adjustment += reduction
            adjustment_reasons.append("Low traffic pressure: Conditions are highly stable")

        final_smart_eta = round(google_duration + delay_adjustment, 2)
        if final_smart_eta < primary['normal_duration']:
            final_smart_eta = primary['normal_duration'] # Cannot be faster than free flow usually

        # 4. Route Risk Analysis
        risk_level = "Low"
        stability = "Stable"
        if pressure_score > 60 or display_congestion == "High":
            risk_level = "High"
            stability = "Volatile"
        elif pressure_score > 35 or display_congestion == "Medium":
            risk_level = "Medium"
            stability = "Fluctuating"

        # 5. AI Reasoning Section
        ai_reasons = []
        if pressure_score < 30:
            ai_reasons.append("✓ Low traffic pressure")
            pressure_trend = "stable"
        elif pressure_score < 60:
            ai_reasons.append("⚠ Moderate traffic pressure")
            pressure_trend = "rising"
        else:
            ai_reasons.append("⚠ High traffic pressure")
            pressure_trend = "highly rising"

        if context.get('weather_condition') == "Clear": ai_reasons.append("✓ Clear weather")
        elif context.get('rainfall_status') == "Rain": ai_reasons.append("⚠ Heavy rainfall")
        else: ai_reasons.append(f"✓ {context.get('weather_condition')} weather")

        if not context.get('office_rush_hour_indicator') and not context.get('school_hours_indicator'):
            ai_reasons.append("✓ Outside rush hour")
        else:
            if context.get('office_rush_hour_indicator'): ai_reasons.append("⚠ Office rush hour")
            if context.get('school_hours_indicator') and not context.get('school_holiday_indicator'): ai_reasons.append("⚠ School rush hour")

        if stability == "Stable": ai_reasons.append("✓ Stable traffic pattern")
        else: ai_reasons.append(f"⚠ {stability} road conditions")

        # 6. Recommendation
        recommendation = self._generate_recommendation(
            google_congestion, model_congestion, context, delay_adjustment, google_data['alternatives']
        )

        # 7. Speed calculation
        avg_speed = round(primary['distance'] / (final_smart_eta / 60), 2) if final_smart_eta > 0 else 0

        # Build Response
        response = {
            "status": "success",
            "departure": google_data['origin'],
            "destination": google_data['destination'],
            "distance": primary['distance'],
            "travel_time": final_smart_eta,
            "normal_duration": primary['normal_duration'],
            "google_traffic_duration": google_duration,
            "ai_adjustment": round(delay_adjustment, 2),
            "final_smart_eta": final_smart_eta,
            "adjustment_reasons": adjustment_reasons,
            "speed": avg_speed,
            "congestion": display_congestion,
            "confidence_score": model_confidence,
            "probabilities": probabilities,
            "traffic_pressure_score": pressure_score,
            "pressure_level": "Low" if pressure_score < 30 else ("Medium" if pressure_score < 70 else "High"),
            "pressure_trend": pressure_trend,
            "context_analysis": {
                "weather": context['weather_condition'],
                "rainfall": context['rainfall_status'],
                "school_rush": "Yes" if context['school_hours_indicator'] and not context['school_holiday_indicator'] else "No",
                "office_rush": "Yes" if context['office_rush_hour_indicator'] else "No",
                "event": "Yes" if context['event_indicator'] else "No",
                "holiday": "Yes" if context['holiday_indicator'] else "No"
            },
            "risk_analysis": {
                "level": risk_level,
                "stability": stability
            },
            "ai_reasoning": ai_reasons,
            "smart_recommendation": recommendation,
            "polyline": primary['polyline'],
            "segments_delay": primary['segments_delay'],
            "is_prediction": google_data.get('is_prediction', False),
            "hour": context['hour'],
            "day": datetime.fromtimestamp(int(google_data.get('departure_time', 0))).strftime("%A") if isinstance(google_data.get('departure_time'), (int, float, str)) and str(google_data.get('departure_time')).isdigit() else datetime.now().strftime("%A")
        }

        # Debugging & Validation
        logger.debug(
            "AI prediction %s -> %s: google_eta=%s ai_adj=%s smart_eta=%s confidence=%s%% pressure=%s",
            response['departure'], response['destination'],
            google_duration, delay_adjustment, final_smart_eta,
            model_confidence, pressure_score,
        )

        return response

    def _generate_recommendation(self, g_cong, m_cong, context, delay, alternatives):
        """Generates a human-readable recommendation."""
        reasons = []
        if context.get('rainfall_status') == "Rain": reasons.append("heavy rain")
        if context.get('school_hours_indicator'): reasons.append("school rush hour")
        if context.get('event_indicator'): reasons.append(f"a local event ({context.get('event_type')})")
        if context.get('office_rush_hour_indicator'): reasons.append("office rush hour")

        reason_str = ", ".join(reasons) if reasons else "current traffic trends"

        msg = f"{m_cong} congestion likely near destination"
        if reasons:
            msg += f" due to {reason_str}."
        else:
            msg += "."

        if delay > 0:
            msg += f" Suggested delay adjustment: +{round(delay, 1)} mins."

        if alternatives:
            msg += f" Alternative Route {alternatives[0]['summary']} is also available."

        if m_cong == "High":
            msg += " Consider departing 30 minutes later for smoother travel."
        else:
            msg += " Conditions are relatively stable."

        return msg
