"""
Single Google Maps Directions client.

Previously the same "clean the location, call the Directions API, pull
distance/duration/duration_in_traffic off the first leg" logic was copy-pasted in
three places (``GoogleMapsService``, ``utils.get_realtime_traffic`` and
``collector.fetch_google_traffic``), with subtly different timeouts and congestion
thresholds. This module is the one place that talks to Google; each caller layers
its own domain shaping on top of :meth:`DirectionsClient.fetch` /
:func:`parse_leg_metrics`.
"""
import requests
from django.conf import settings

GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"


class DirectionsError(Exception):
    """Raised for a missing API key, a non-OK API status, or a network error."""


def clean_location(location):
    """Add regional context (Buea, Cameroon) unless already present."""
    location = location.strip()
    if "buea" not in location.lower():
        return f"{location}, Buea, Cameroon"
    return location


def parse_leg_metrics(leg):
    """Extract the common metrics from a Directions API ``leg``.

    Returns ``(distance_km, duration_min, duration_in_traffic_min)``. Falls back
    to plain duration when ``duration_in_traffic`` is absent (e.g. past times).
    """
    distance_km = leg["distance"]["value"] / 1000
    duration_min = leg["duration"]["value"] / 60
    duration_traffic_min = leg.get("duration_in_traffic", leg["duration"])["value"] / 60
    return distance_km, duration_min, duration_traffic_min


class DirectionsClient:
    """Thin wrapper around the Google Directions API."""

    def __init__(self, api_key=None, timeout=10):
        self.api_key = api_key if api_key is not None else getattr(settings, "GOOGLE_MAPS_API_KEY", None)
        self.timeout = timeout

    def fetch(self, origin, destination, departure_time="now", alternatives=False, timeout=None):
        """
        Call the Directions API and return ``(origin_clean, dest_clean, data)``
        where ``data`` is the parsed response with ``status == 'OK'``.

        Raises :class:`DirectionsError` on a missing key, network failure, or a
        non-OK API status.
        """
        if not self.api_key:
            raise DirectionsError("Google API Key not configured")

        origin_clean = clean_location(origin)
        dest_clean = clean_location(destination)
        params = {
            "origin": origin_clean,
            "destination": dest_clean,
            "departure_time": departure_time,
            "traffic_model": "best_guess",
            "key": self.api_key,
        }
        if alternatives:
            params["alternatives"] = True

        try:
            response = requests.get(
                GOOGLE_DIRECTIONS_URL, params=params, timeout=timeout or self.timeout
            )
            data = response.json()
        except Exception as exc:
            raise DirectionsError(str(exc))

        if data.get("status") != "OK":
            raise DirectionsError(f"Google Maps API Error: {data.get('status')}")
        return origin_clean, dest_clean, data
