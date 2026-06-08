from datetime import datetime, time
from .logger import logger

# Weekday integers as produced by datetime.weekday(): Mon=0 ... Sun=6.
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


class EventDetector:
    """
    Detects local context that affects traffic.

    Markets are *location-aware*: a market only flags a trip whose origin or
    destination is at (or near) the market's spot on the days that market runs.
    This replaces the previous behaviour, where every route was flagged on
    Fri/Sat/Sun regardless of location (a duplicate of ``day_of_week``).

    Severity is a deliberate placeholder ("Medium"): we do not yet have ground
    truth that markets slow traffic, so it must not be presented as a measured
    fact. It exists so the existing ``event_severity`` feature keeps a value.
    """

    # Real, recurring Buea markets. ``nodes`` are matched against the trip's
    # origin/destination (the named spots in the route vocabulary).
    MARKETS = {
        "Muea Market": {"days": {THU, SUN}, "nodes": ["Muea"]},
        "Great Soppo Market (OIC)": {"days": {MON, TUE, WED, THU, FRI, SAT, SUN}, "nodes": ["Great Soppo"]},
        "Buea Central Market": {"days": {SAT, SUN}, "nodes": ["Check Point"]},
        "Buea Town Market": {"days": {MON, WED, FRI}, "nodes": ["Buea Town"]},
    }

    def __init__(self):
        # Specific dates for major city-wide events (affect all routes).
        # Populate with real, dated events (e.g. national days, big matches).
        self.FIXED_EVENTS = {
            # "2026-02-11": {"type": "Youth Day Celebrations", "severity": "High"},
            # "2026-05-20": {"type": "National Day", "severity": "High"},
        }

        # Office hours and rush hours
        self.OFFICE_MORNING_RUSH = (time(6, 30), time(9, 0))
        self.OFFICE_EVENING_RUSH = (time(16, 0), time(19, 30))
        self.WORKING_HOURS = (time(8, 0), time(17, 0))

    @staticmethod
    def _matches(node, *places):
        """True if ``node`` appears in any of the supplied origin/destination strings."""
        node_l = node.lower()
        return any(place and node_l in str(place).lower() for place in places)

    def active_markets(self, dt, origin=None, destination=None):
        """Return the list of market names active for this day + trip endpoints."""
        weekday = dt.weekday()
        hits = []
        for name, cfg in self.MARKETS.items():
            if weekday not in cfg["days"]:
                continue
            if any(self._matches(node, origin, destination) for node in cfg["nodes"]):
                hits.append(name)
        return hits

    def get_event_info(self, dt=None, origin=None, destination=None):
        """
        Event/market context for a trip.

        City-wide ``FIXED_EVENTS`` take precedence (they affect every route).
        Otherwise, markets are applied only when the trip touches the market's
        spot. With no origin/destination, only city-wide fixed events fire
        (markets are location-specific and need endpoints to match).
        """
        if dt is None:
            dt = datetime.now()

        date_str = dt.strftime("%Y-%m-%d")

        # 1. City-wide fixed events first.
        if date_str in self.FIXED_EVENTS:
            event = self.FIXED_EVENTS[date_str]
            return {
                "event_indicator": 1,
                "event_type": event["type"],
                "event_severity": event["severity"],
            }

        # 2. Location-aware markets.
        markets = self.active_markets(dt, origin, destination)
        if markets:
            return {
                "event_indicator": 1,
                "event_type": " & ".join(markets),
                "event_severity": "Medium",
            }

        return {"event_indicator": 0, "event_type": "None", "event_severity": "Low"}

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
