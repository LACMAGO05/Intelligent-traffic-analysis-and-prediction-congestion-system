import holidays
from datetime import date
from django.core.cache import cache
from .logger import logger

# Holiday status for a given date never changes; cache it for a day.
_HOLIDAY_CACHE_TTL = 86400  # seconds (24 hours)

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

        cache_key = f"holiday:CM:{check_date.isoformat()}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        indicator = 1 if check_date in self.cm_holidays else 0
        cache.set(cache_key, indicator, _HOLIDAY_CACHE_TTL)
        return indicator

    def get_holiday_name(self, check_date=None):
        if check_date is None:
            check_date = date.today()
        return self.cm_holidays.get(check_date, "No Holiday")
