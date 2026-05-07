from datetime import datetime, time
from .logger import logger

class SchoolService:
    def __init__(self):
        # Example configuration for school holidays
        self.SCHOOL_HOLIDAYS = [
            ("2026-06-15", "2026-09-01"),
            ("2026-12-15", "2027-01-05"),
            ("2027-04-01", "2027-04-15"), # Easter break estimate
        ]
        
        # School rush hours
        self.MORNING_RUSH = (time(6, 30), time(8, 0))
        self.CLOSING_RUSH = (time(13, 0), time(15, 0))

    def is_school_holiday(self, check_date=None):
        if check_date is None:
            check_date = datetime.now().date()
        
        for start_str, end_str in self.SCHOOL_HOLIDAYS:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            if start_date <= check_date <= end_date:
                return 1
        return 0

    def is_school_rush_hour(self, check_time=None):
        if check_time is None:
            check_time = datetime.now().time()
        
        # Morning rush
        if self.MORNING_RUSH[0] <= check_time <= self.MORNING_RUSH[1]:
            return 1
        
        # Closing rush
        if self.CLOSING_RUSH[0] <= check_time <= self.CLOSING_RUSH[1]:
            return 1
            
        return 0

    def get_indicators(self, dt=None):
        if dt is None:
            dt = datetime.now()
        
        return {
            "school_holiday_indicator": self.is_school_holiday(dt.date()),
            "school_hours_indicator": self.is_school_rush_hour(dt.time())
        }
