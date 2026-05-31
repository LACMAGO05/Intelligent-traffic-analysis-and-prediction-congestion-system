import requests
import re
from django.conf import settings

class GoogleMapsService:
    """
    Service to handle interactions with Google Maps APIs.
    Responsible for fetching route details including duration, distance, polyline, and alternatives.
    """

    def __init__(self):
        # API Key is retrieved from Django settings (kept in environment variables)
        self.api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        self.base_url = "https://maps.googleapis.com/maps/api/directions/json"

    def _clean_location(self, location):
        """
        Ensures the location has regional context (Buea, Cameroon) if not already present.
        This improves the accuracy of the Google Maps search.
        """
        location = location.strip()
        if "buea" not in location.lower():
            return f"{location}, Buea, Cameroon"
        return location

    def get_route_details(self, origin, destination, departure_time="now"):
        """
        Calls Google Maps Directions API to get detailed route information.

        Parameters:
            origin (str): Starting point
            destination (str): End point
            departure_time (str/int): 'now' or a unix timestamp for future predictions

        Returns:
            dict: Structured JSON with route details or error message
        """
        if not self.api_key:
            return {"error": "Google API Key not configured"}

        origin_clean = self._clean_location(origin)
        dest_clean = self._clean_location(destination)

        # Parameters for the Directions API
        # alternatives=True allows us to get more than one route option
        params = {
            "origin": origin_clean,
            "destination": dest_clean,
            "departure_time": departure_time,
            "traffic_model": "best_guess",
            "alternatives": True,
            "key": self.api_key
        }

        try:
            # Make the request to Google Maps
            response = requests.get(self.base_url, params=params, timeout=10)
            data = response.json()

            # Check if the API returned a successful status
            if data['status'] != 'OK':
                return {"error": f"Google Maps API Error: {data['status']}"}

            routes = []
            for idx, route in enumerate(data['routes']):
                leg = route['legs'][0]

                # Extract basic metrics
                distance_km = leg['distance']['value'] / 1000
                duration_min = leg['duration']['value'] / 60

                # duration_in_traffic is only available for 'now' or future departure_time requests
                # If not present, fallback to normal duration
                duration_traffic_min = leg.get('duration_in_traffic', leg['duration'])['value'] / 60

                # Analyze steps for specific segment delays
                segments_delay = []
                for step in leg['steps']:
                    html_instructions = step.get('html_instructions', "")
                    step_duration = step['duration']['value'] / 60
                    step_duration_traffic = step.get('duration_in_traffic', {}).get('value', step['duration']['value']) / 60

                    step_delay = step_duration_traffic - step_duration

                    if step_delay > 1:
                        # Clean HTML from instructions to get a readable segment name
                        clean_instruction = re.sub('<[^<]+?>', '', html_instructions)
                        segments_delay.append({
                            "point": clean_instruction,
                            "delay": round(step_delay, 1)
                        })

                # Compile structured data for each route
                routes.append({
                    "route_index": idx,
                    "summary": route.get('summary', 'Main Route'),
                    "distance": round(distance_km, 2),
                    "normal_duration": round(duration_min, 2),
                    "traffic_duration": round(duration_traffic_min, 2),
                    "polyline": route['overview_polyline']['points'],
                    "segments_delay": segments_delay
                })

            # Return the first route as primary, and others as alternatives
            return {
                "status": "success",
                "origin": origin_clean,
                "destination": dest_clean,
                "primary_route": routes[0],
                "alternatives": routes[1:] if len(routes) > 1 else [],
                "is_prediction": departure_time != "now"
            }

        except Exception as e:
            # Handle unexpected errors (network issues, etc.)
            return {"error": f"Service Error: {str(e)}"}
