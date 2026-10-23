from rest_framework import serializers

from jobs.models import JobEvent, Notification

class JobEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobEvent
        fields = [
            "id",
            "job",
            "event_type",
            "message",
            "metadata",
            "created_at",
        ]

        read_only_fields = fields 

class NotificationSerializer(serializers.ModelSerializer):
    job_id = serializers.IntegerField(
        source = "job.id",
        read_only = True,
        allow_null = True,
    )

    event_id = serializers.IntegerField(
        source = "event.id",
        read_only = True,
        allow_null = True,
    )

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "job_id",
            "event_id",
            "is_read",
            "created_at",
            "read_at",
        ]

        read_only_fields = fields 

        