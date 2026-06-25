import re

from django.core.cache import cache

from traffic_context.directions_client import DirectionsClient, DirectionsError, parse_leg_metrics

# Each Directions lookup is a paid Google call. Live traffic only changes minute
# to minute, so caching identical (origin, destination, time-bucket) lookups for
# a short window cuts both cost and latency without users noticing staleness.
_CACHE_TTL = 120  # seconds


class GoogleMapsService:
    """
    Service to handle interactions with Google Maps APIs.
    Responsible for fetching route details including duration, distance, polyline, and alternatives.
    """

    def __init__(self):
        # Single shared Directions client (handles the API key + HTTP call).
        self.client = DirectionsClient()

    @staticmethod
    def _cache_key(origin, destination, departure_time):
        # Bucket "now" into 2-minute windows; future timestamps into the hour
        # they fall in, so identical forecasts reuse one API call.
        if departure_time == "now":
            import time
            bucket = int(time.time() // _CACHE_TTL)
        else:
            bucket = int(departure_time) // 3600
        return f"directions:{origin.strip().lower()}|{destination.strip().lower()}|{bucket}"

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
        cache_key = self._cache_key(origin, destination, departure_time)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            origin_clean, dest_clean, data = self.client.fetch(
                origin, destination, departure_time, alternatives=True
            )
        except DirectionsError as e:
            return {"error": str(e)}

        try:
            routes = []
            for idx, route in enumerate(data['routes']):
                leg = route['legs'][0]

                # Extract basic metrics (distance_km, normal/traffic durations)
                distance_km, duration_min, duration_traffic_min = parse_leg_metrics(leg)

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
            result = {
                "status": "success",
                "origin": origin_clean,
                "destination": dest_clean,
                "primary_route": routes[0],
                "alternatives": routes[1:] if len(routes) > 1 else [],
                "is_prediction": departure_time != "now"
            }
            cache.set(cache_key, result, _CACHE_TTL)  # only successful lookups cached
            return result

        except Exception as e:
            # Handle unexpected errors (network issues, etc.)
            return {"error": f"Service Error: {str(e)}"}
