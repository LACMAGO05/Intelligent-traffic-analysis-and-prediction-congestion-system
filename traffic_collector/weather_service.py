import requests
import os
from django.conf import settings
from .logger import logger

class WeatherService:
    def __init__(self):
        self.api_key = getattr(settings, "OPENWEATHER_API_KEY", None)
        self.city = "Buea,CM"
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"

    def get_current_weather(self):
        if not self.api_key:
            logger.warning("OpenWeatherMap API Key missing. Skipping weather collection.")
            return {
                "weather_condition": "Unknown",
                "rainfall_status": "No Rain"
            }

        params = {
            "q": self.city,
            "appid": self.api_key,
            "units": "metric"
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            if response.status_code == 401:
                logger.error("OpenWeatherMap API Error: Unauthorized (401). "
                             "Please check if your API key is valid and active.")
                return {
                    "weather_condition": "Unauthorized",
                    "rainfall_status": "Unknown"
                }
            response.raise_for_status()
            data = response.json()

            weather_main = data.get("weather", [{}])[0].get("main", "Clear")
            
            # OpenWeatherMap 'Rain' or 'Drizzle' or 'Thunderstorm' usually implies rainfall
            has_rain = "Rain" in weather_main or "Drizzle" in weather_main or "Thunderstorm" in weather_main
            
            return {
                "weather_condition": weather_main,
                "rainfall_status": "Rain" if has_rain else "No Rain"
            }
        except Exception as e:
            logger.error(f"Error fetching weather data: {e}")
            return {
                "weather_condition": "Error",
                "rainfall_status": "Unknown"
            }
