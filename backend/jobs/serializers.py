from rest_framework import serializers
from .models import Job, DailyJobSummary

class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            "id",
            "file",
            "status",
            "progress",
            "error_message",
            "cancel_requested",
            "created_at",
            "completed_at",
        ]

        read_only_fields = [
            "id",
            "status",
            "progress",
            "error_message",
            "cancel_requested",
            "created_at",
            "completed_at",
        ]

class DailyJobSummarySerializer(serializers.ModelSerializer):
    """
    Serializer stored daily job summary records.

    All fields are read-only because this API only retrives 
    previously generated summaries.
    """

    class Meta:
        model = DailyJobSummary

        fields = [
            "summary_date",
            "total_jobs",
            "pending_jobs",
            "processing_jobs",
            "retrying_jobs",
            "completed_jobs",
            "failed_jobs",
            "cancelled_jobs",
            "run_status",
            "error_message",
            "started_at",
            "completed_at",            
        ]

        read_only_fileds = fields

        

    