import uuid
from django.db import models
from django.contrib.auth.models import User

class ChatThread(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_threads")
    title = models.CharField(max_length=255, default="New Analysis")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_thread_user_created"),
        ]

    def __str__(self):
        return f"Thread {self.title} for {self.user.username}"

class ChatMessage(models.Model):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="messages", null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_messages")
    message = models.TextField()
    response = models.JSONField()  # Store the full JSON response from the traffic API
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["thread", "timestamp"], name="idx_message_thread_time"),
        ]

    def __str__(self):
        return f"Chat for {self.user.username} at {self.timestamp}"


class TrafficRecord(models.Model):
    """
    Durable store for the background traffic-collection pipeline.

    This replaces the append-only ``google_traffic_data_v2.csv`` as the source of
    truth: writes are concurrency-safe and de-duplication is enforced by a unique
    ``(timestamp, route)`` constraint instead of scanning the tail of a file.
    Export it back to CSV with ``manage.py export_training_data`` when retraining.
    """
    timestamp = models.DateTimeField()
    route = models.CharField(max_length=255)
    distance_km = models.FloatField(null=True, blank=True)
    hour = models.IntegerField(null=True, blank=True)
    day = models.CharField(max_length=16, blank=True, default="")
    day_of_week = models.IntegerField(null=True, blank=True)
    travel_time_mins = models.FloatField(null=True, blank=True)
    speed_kmh = models.FloatField(null=True, blank=True)
    congestion = models.CharField(max_length=16, blank=True, default="")
    weather_condition = models.CharField(max_length=32, blank=True, default="")
    rainfall_status = models.CharField(max_length=32, blank=True, default="")
    holiday_indicator = models.IntegerField(default=0)
    school_holiday_indicator = models.IntegerField(default=0)
    school_hours_indicator = models.IntegerField(default=0)
    working_hours_indicator = models.IntegerField(default=0)
    office_rush_hour_indicator = models.IntegerField(default=0)
    event_indicator = models.IntegerField(default=0)
    event_type = models.CharField(max_length=64, blank=True, default="")
    event_severity = models.CharField(max_length=16, blank=True, default="")
    traffic_pressure_score = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        constraints = [
            models.UniqueConstraint(fields=["timestamp", "route"], name="uniq_traffic_timestamp_route"),
        ]
        indexes = [
            models.Index(fields=["route", "timestamp"], name="idx_traffic_route_time"),
            models.Index(fields=["congestion"], name="idx_traffic_congestion"),
        ]

    def __str__(self):
        return f"{self.route} @ {self.timestamp} ({self.congestion})"


class TaskOutbox(models.Model):
    """
    Durable queue for fire-and-forget work (currently transactional emails).

    Replaces the in-process thread pool: a task is persisted here, then the
    background worker drains it with retries. This means a dyno restart can't
    silently lose a welcome/alert email. ``payload`` must be JSON-serialisable
    and ``task`` must name an entry in the outbox TASK_REGISTRY.
    """
    STATUS_PENDING = "pending"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"

    task = models.CharField(max_length=80)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, default=STATUS_PENDING, db_index=True)
    attempts = models.IntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="idx_outbox_status"),
        ]

    def __str__(self):
        return f"{self.task} [{self.status}]"


class PushSubscription(models.Model):
    """
    A browser Web Push subscription for a user (one per device/browser).

    Stores the endpoint and the two keys the Push API hands us at subscribe
    time; these are what ``pywebpush`` needs to deliver a notification, even
    when the site's tab is closed.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.URLField(max_length=600, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=400, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PushSubscription({self.user.username})"


class RouteWatch(models.Model):
    """
    A route a user explicitly wants gridlock alerts for.

    The background alert job forecasts each active watch ~1 hour ahead and sends
    a push notification if a gridlock is likely (and not already alerted). Days
    are stored as a comma-separated list of weekday numbers (0=Mon); empty means
    every day. The optional time window narrows alerts to a commute period.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="route_watches"
    )
    origin = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    # "" = every day; otherwise e.g. "0,1,2,3,4" for weekdays.
    days = models.CharField(max_length=20, blank=True, default="")
    window_start = models.TimeField(null=True, blank=True)
    window_end = models.TimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "origin", "destination"], name="uniq_user_route_watch"
            ),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.origin}→{self.destination}"


class TrafficAlert(models.Model):
    """
    Log of a gridlock alert already sent — used to deduplicate so a user is not
    notified repeatedly for the same predicted congestion window.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="traffic_alerts"
    )
    route_watch = models.ForeignKey(
        RouteWatch, on_delete=models.CASCADE, related_name="alerts", null=True, blank=True
    )
    route = models.CharField(max_length=255)
    # The predicted congestion time this alert was about (truncated to the hour),
    # so re-runs within the same window don't re-notify.
    alert_for = models.DateTimeField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "route", "alert_for"], name="uniq_alert_window"
            ),
        ]

    def __str__(self):
        return f"Alert {self.route} @ {self.alert_for:%Y-%m-%d %H:%M} → {self.user.username}"


class AnalyticsEvent(models.Model):
    """
    Lightweight product-analytics event log — one row per event.

    Used to measure the guest → signup conversion funnel. The optional
    ``session_key`` lets anonymous activity (guest predictions, hitting the
    trial wall) be attributed to a signup that happens later in the same
    browser session; ``user`` is filled once the visitor has an account.
    """
    EVENT_GUEST_PREDICTION = "guest_prediction"
    EVENT_WALL_HIT = "wall_hit"
    EVENT_SIGNUP = "signup_completed"
    EVENT_GUEST_CONVERTED = "guest_converted"

    event = models.CharField(max_length=40, db_index=True)
    session_key = models.CharField(max_length=40, blank=True, default="", db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="analytics_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event", "created_at"], name="idx_event_created"),
        ]

    def __str__(self):
        return f"{self.event} @ {self.created_at:%Y-%m-%d %H:%M}"


class TrustedDevice(models.Model):
    """
    A browser/device that has already passed new-device email verification.

    Login issues a session immediately only when the incoming request carries a
    cookie whose token matches a non-expired row here. Otherwise the user is
    challenged with an emailed one-time code (step-up verification), mirroring the
    "new sign-in on a new device" check used by major providers.

    Only the SHA-256 *hash* of the device token is stored; the raw token lives
    solely in the user's cookie, so a database leak can't be replayed as a device.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="trusted_devices"
    )
    token_hash = models.CharField(max_length=64, db_index=True)
    user_agent = models.CharField(max_length=400, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-last_seen"]
        indexes = [
            models.Index(fields=["user", "token_hash"], name="idx_trusted_user_token"),
        ]

    def __str__(self):
        return f"TrustedDevice for {self.user.username} (exp {self.expires_at:%Y-%m-%d})"


class PredictionLog(models.Model):
    """
    Per-prediction log written by ``predict_view``.

    Kept separate from :class:`TrafficRecord` so the prediction-time schema and
    the training-dataset schema can never collide in a single file (the previous
    behaviour that produced a ragged CSV). Also backs the analytics dashboard.
    """
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="prediction_logs"
    )
    origin = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    distance = models.FloatField(null=True, blank=True)
    hour = models.IntegerField(null=True, blank=True)
    day = models.CharField(max_length=16, blank=True, default="")
    travel_time = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    congestion = models.CharField(max_length=16, blank=True, default="")
    # ML model confidence (%) for this prediction. Persisted so model drift can
    # be monitored over time (a falling trend flags a degrading/stale model).
    confidence = models.FloatField(null=True, blank=True)
    is_prediction = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["congestion"], name="idx_predlog_congestion"),
            models.Index(fields=["created_at"], name="idx_predlog_created"),
        ]

    def __str__(self):
        return f"{self.origin} -> {self.destination} ({self.congestion})"
