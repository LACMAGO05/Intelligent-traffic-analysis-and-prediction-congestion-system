# Generated manually for durable background-job claims.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("TrafficApp", "0007_predictionlog_confidence_taskoutbox"),
    ]

    operations = [
        migrations.AddField(
            model_name="taskoutbox",
            name="locked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trafficalert",
            name="status",
            field=models.CharField(
                choices=[("pending", "Pending"), ("sent", "Sent")],
                default="sent",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="trafficalert",
            name="claim_token",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trafficalert",
            name="lease_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="trafficalert",
            name="sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
