import random
from django.utils import timezone
import datetime
from traffic_context.directions_client import DirectionsClient, DirectionsError, parse_leg_metrics

def generate_otp():
    return str(random.randint(100000, 999999))

def get_realtime_traffic(origin, destination, departure_time="now"):
    """
    Fetches traffic data from Google Directions API to provide segment-specific delays.
    Can be for 'now' or a specific timestamp.
    """
    try:
        origin_clean, dest_clean, data = DirectionsClient().fetch(origin, destination, departure_time)
    except DirectionsError as e:
        return {"error": str(e)}

    try:
        route = data['routes'][0]
        leg = route['legs'][0]

        duration_km, duration_min, duration_traffic_min = parse_leg_metrics(leg)

        # Segment-specific delay identification
        segments_delay = []
        
        for step in leg['steps']:
            html_instructions = step.get('html_instructions', "")
            step_duration = step['duration']['value'] / 60
            
            # Google Directions API sometimes provides duration_in_traffic for each step
            # if the departure_time is specified and the user has the right API access.
            # Otherwise, we can use a heuristic.
            
            # Let's see if we have duration_in_traffic for the step
            step_duration_traffic = step.get('duration_in_traffic', {}).get('value', step['duration']['value']) / 60
            
            step_delay = step_duration_traffic - step_duration
            
            # If there's a significant delay in this step (more than 1 minute)
            if step_delay > 1:
                # Clean HTML tags from instructions to get a clean segment name
                import re
                clean_instruction = re.sub('<[^<]+?>', '', html_instructions)
                
                segments_delay.append({
                    "point": clean_instruction,
                    "delay": round(step_delay, 1)
                })
            else:
                # Fallback to choke points if no specific step delay is found but overall ratio is high
                choke_points = ["Bonduma Gate", "Malingo Junction", "Mile 17", "Great Soppo", "Check Point", "University of Buea"]
                for cp in choke_points:
                    if cp.lower() in html_instructions.lower():
                        ratio = duration_traffic_min / duration_min if duration_min > 0 else 1
                        if ratio > 1.2:
                            total_delay = max(0, duration_traffic_min - duration_min)
                            # Estimate this segment's contribution
                            segment_delay_estimate = round(total_delay * (step_duration / duration_min), 1)
                            if segment_delay_estimate > 0.5:
                                segments_delay.append({
                                    "point": cp,
                                    "delay": segment_delay_estimate
                                })
                                break # Avoid double counting for same step

        # Compute speed (km/h)
        speed = duration_km / (duration_traffic_min / 60) if duration_traffic_min > 0 else 0

        # Compute congestion level
        ratio = duration_traffic_min / duration_min if duration_min > 0 else 1
        if ratio < 1.2:
            congestion = "Low"
        elif ratio < 1.5:
            congestion = "Medium"
        else:
            congestion = "High"

        if isinstance(departure_time, int):
            dt = datetime.datetime.fromtimestamp(departure_time, tz=datetime.timezone.utc)
            dt = timezone.localtime(dt)
        else:
            dt = timezone.now()

        return {
            "route": f"{origin}-{destination}",
            "distance": round(duration_km, 2),
            "hour": dt.hour,
            "day": dt.strftime("%A"),
            "travel_time": round(duration_traffic_min, 2),
            "normal_duration": round(duration_min, 2),
            "speed": round(speed, 2),
            "congestion": congestion,
            "segments_delay": segments_delay,
            "status": "success",
            "is_prediction": departure_time != "now"
        }
    except Exception as e:
        return {"error": str(e)}

def find_best_departure_time(origin, destination):
    """
    Checks future departure times (30, 60, 90 mins from now)
    to find a time with lower congestion.
    """
    now = int(timezone.now().timestamp())
    offsets = [30, 60, 90] # minutes
    
    current_traffic = get_realtime_traffic(origin, destination, departure_time="now")
    if current_traffic.get("congestion") == "Low" or "error" in current_traffic:
        return None

    best_time = None
    
    for offset in offsets:
        future_time = now + (offset * 60)
        future_traffic = get_realtime_traffic(origin, destination, departure_time=future_time)
        
        if "error" in future_traffic:
            continue
            
        if future_traffic.get("congestion") == "Low":
            # Found a good time
            dt = datetime.datetime.fromtimestamp(future_time, tz=datetime.timezone.utc)
            local_dt = timezone.localtime(dt)
            return {
                "time": local_dt.strftime("%H:%M"),
                "congestion": "Low",
                "travel_time": future_traffic.get("travel_time")
            }
        
        # If it's Medium and current is High, it's an improvement
        if current_traffic.get("congestion") == "High" and future_traffic.get("congestion") == "Medium":
            if not best_time:
                dt = datetime.datetime.fromtimestamp(future_time, tz=datetime.timezone.utc)
                local_dt = timezone.localtime(dt)
                best_time = {
                    "time": local_dt.strftime("%H:%M"),
                    "congestion": "Medium",
                    "travel_time": future_traffic.get("travel_time")
                }
    
    return best_time
