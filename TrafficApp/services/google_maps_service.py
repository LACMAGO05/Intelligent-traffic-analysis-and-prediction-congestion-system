import re
from traffic_context.directions_client import DirectionsClient, DirectionsError, parse_leg_metrics

class GoogleMapsService:
    """
    Service to handle interactions with Google Maps APIs.
    Responsible for fetching route details including duration, distance, polyline, and alternatives.
    """

    def __init__(self):
        # Single shared Directions client (handles the API key + HTTP call).
        self.client = DirectionsClient()

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
