import holidays
from datetime import date
from .logger import logger

class HolidayService:
    def __init__(self):
        # Cameroon public holidays
        try:
            self.cm_holidays = holidays.CountryHoliday('CM')
        except Exception as e:
            logger.error(f"Error initializing holidays library: {e}")
            self.cm_holidays = {}

    def is_public_holiday(self, check_date=None):
        if check_date is None:
            check_date = date.today()
        
        indicator = 1 if check_date in self.cm_holidays else 0
        return indicator

    def get_holiday_name(self, check_date=None):
        if check_date is None:
            check_date = date.today()
        return self.cm_holidays.get(check_date, "No Holiday")
