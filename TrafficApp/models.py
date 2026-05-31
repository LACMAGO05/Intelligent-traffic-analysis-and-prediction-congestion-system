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
