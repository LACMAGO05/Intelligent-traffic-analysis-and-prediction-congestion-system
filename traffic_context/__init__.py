"""
Neutral package of shared traffic-context providers.

These modules (weather, holidays, school/office schedules, events, congestion
classification, pressure scoring, feature engineering, logging) used to live in
``traffic_collector`` and were imported directly by the web prediction service,
which tightly coupled the request path to the background collector.

They now live here so both consumers — ``TrafficApp.services`` (online
prediction) and ``traffic_collector`` (offline collection) — depend on this
neutral package instead of on each other.
"""
