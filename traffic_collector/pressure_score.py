class PressureScoreCalculator:
    def calculate(self, data):
        """
        Intelligently combine factors into a 0-100 score.
        Factors:
        - office rush (15 pts)
        - school rush (15 pts)
        - weather/rain (10 pts)
        - public holidays (10 pts)
        - school holidays (-10 pts reduction to rush)
        - events (10 pts)
        - weekend (5 pts)
        - congestion (40 pts)
        - time of day (5 pts)
        """
        score = 0
        
        # Office rush
        if data.get('office_rush_hour_indicator'):
            score += 15
            
        # School rush - reduced if school holiday
        if data.get('school_hours_indicator'):
            if data.get('school_holiday_indicator'):
                score += 5
            else:
                score += 15
                
        # Weather
        if data.get('rainfall_status') == "Rain":
            score += 10
        elif data.get('weather_condition') not in ["Clear", "Cloudy"]:
            score += 5
            
        # Public Holiday
        if data.get('holiday_indicator'):
            score += 10
            
        # Events
        if data.get('event_indicator'):
            severity = data.get('event_severity', 'Low')
            if severity == 'High':
                score += 15
            elif severity == 'Medium':
                score += 10
            else:
                score += 5
                
        # Weekend
        if data.get('day_of_week') in [5, 6]: # Sat, Sun
            score += 5
            
        # Congestion (Crucial factor)
        congestion = data.get('congestion', 'Low')
        if congestion == 'High':
            score += 40
        elif congestion == 'Medium':
            score += 20
            
        # Time of day (Night is usually lower pressure, but we account for it)
        hour = data.get('hour', 12)
        if 7 <= hour <= 19:
            score += 5

        # Cap at 100
        return min(100, score)
