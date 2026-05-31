from datetime import datetime, time
from .logger import logger

class EventDetector:
    def __init__(self):
        # Configurable event rules based on day of week
        self.WEEKLY_EVENTS = {
            "Friday": {"type": "Market Activity", "severity": "Medium"},
            "Saturday": {"type": "Heavy Commercial Activity", "severity": "High"},
            "Sunday": {"type": "Church Conventions", "severity": "Medium"},
        }
        
        # Specific dates for major events (could be loaded from a DB later)
        self.FIXED_EVENTS = {
            # "2026-02-11": {"type": "Youth Day Celebrations", "severity": "High"},
            # "2026-05-20": {"type": "National Day", "severity": "High"},
        }

        # Office hours and rush hours
        self.OFFICE_MORNING_RUSH = (time(6, 30), time(9, 0))
        self.OFFICE_EVENING_RUSH = (time(16, 0), time(19, 30))
        self.WORKING_HOURS = (time(8, 0), time(17, 0))

    def get_event_info(self, dt=None):
        if dt is None:
            dt = datetime.now()
        
        date_str = dt.strftime("%Y-%m-%d")
        day_name = dt.strftime("%A")
        
        event_indicator = 0
        event_type = "None"
        event_severity = "Low"
        
        # Check fixed events first
        if date_str in self.FIXED_EVENTS:
            event = self.FIXED_EVENTS[date_str]
            event_indicator = 1
            event_type = event["type"]
            event_severity = event["severity"]
        # Check weekly events
        elif day_name in self.WEEKLY_EVENTS:
            event = self.WEEKLY_EVENTS[day_name]
            event_indicator = 1
            event_type = event["type"]
            event_severity = event["severity"]
            
        return {
            "event_indicator": event_indicator,
            "event_type": event_type,
            "event_severity": event_severity
        }

    def get_office_indicators(self, dt=None):
        if dt is None:
            dt = datetime.now()
        
        check_time = dt.time()
        is_weekend = dt.weekday() >= 5
        
        working_hours_indicator = 0
        office_rush_hour_indicator = 0
        
        if not is_weekend:
            if self.WORKING_HOURS[0] <= check_time <= self.WORKING_HOURS[1]:
                working_hours_indicator = 1
            
            if (self.OFFICE_MORNING_RUSH[0] <= check_time <= self.OFFICE_MORNING_RUSH[1]) or \
               (self.OFFICE_EVENING_RUSH[0] <= check_time <= self.OFFICE_EVENING_RUSH[1]):
                office_rush_hour_indicator = 1
                
        return {
            "working_hours_indicator": working_hours_indicator,
            "office_rush_hour_indicator": office_rush_hour_indicator
        }
