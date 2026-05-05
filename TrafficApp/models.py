import uuid
from django.db import models
from django.contrib.auth.models import User

class ChatThread(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_threads")
    title = models.CharField(max_length=255, default="New Analysis")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Thread {self.title} for {self.user.username}"

class ChatMessage(models.Model):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="messages", null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_messages")
    message = models.TextField()
    response = models.JSONField()  # Store the full JSON response from the traffic API
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Chat for {self.user.username} at {self.timestamp}"
