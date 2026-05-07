import math
import numpy as np

class FeatureEngineer:
    @staticmethod
    def encode_cyclical_hour(hour):
        """Encode hour of day into sine and cosine components."""
        sin_hour = math.sin(2 * math.pi * hour / 24)
        cos_hour = math.cos(2 * math.pi * hour / 24)
        return sin_hour, cos_hour

    @staticmethod
    def add_ml_features(record):
        """Add ML-ready features to the record."""
        hour = record.get('hour', 0)
        sin_h, cos_h = FeatureEngineer.encode_cyclical_hour(hour)
        
        record['sin_hour'] = round(sin_h, 4)
        record['cos_hour'] = round(cos_h, 4)
        
        # Weekend indicator
        day_of_week = record.get('day_of_week', 0)
        record['is_weekend'] = 1 if day_of_week >= 5 else 0
        
        # Peak hour indicator (combined office and school rush)
        record['peak_hour_indicator'] = 1 if (
            record.get('office_rush_hour_indicator') or 
            record.get('school_hours_indicator')
        ) else 0
        
        # Rush hour weight
        weight = 1.0
        if record.get('office_rush_hour_indicator'): weight += 0.5
        if record.get('school_hours_indicator'): weight += 0.5
        if record.get('holiday_indicator'): weight -= 0.3
        record['rush_hour_weight'] = round(max(0.1, weight), 1)
        
        return record
