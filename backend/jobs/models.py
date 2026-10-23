from django.conf import settings
from django.db import models

class Job(models.Model):

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        RETRYING = 'retrying', 'Retrying'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jobs",
    )

    file = models.FileField(upload_to="jobs/")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )


    progress = models.PositiveIntegerField(default=0)

    error_message = models.TextField(blank = True, null=True)

    #Celery task identifier
    celery_task_id = models.CharField(
        max_length = 255,
        blank = True,
        default="",
    )

    retry_count = models.PositiveIntegerField(default=0)

    #Indicates that a user has requested to cancel the job.
    cancel_requested = models.BooleanField(default=False)

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"Job {self.id} = {self.status}"


class DailyJobSummary(models.Model):

    class RunStatus(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    #One summary record per calender date.
    summary_date = models.DateField(unique=True)

    #Job counts for the summary date.
    total_jobs = models.PositiveBigIntegerField(default=0)
    pending_jobs = models.PositiveBigIntegerField(default=0)
    processing_jobs = models.PositiveBigIntegerField(default=0)
    retrying_jobs = models.PositiveBigIntegerField(default=0)
    completed_jobs = models.PositiveBigIntegerField(default=0)
    failed_jobs = models.PositiveBigIntegerField(default=0)
    cancelled_jobs = models.PositiveBigIntegerField(default=0)

    #Execution tracking
    run_status = models.CharField(
        max_length=20,
        choices = RunStatus.choices,
        default = RunStatus.RUNNING,
    )

    error_message = models.TextField(blank=True, null=True)
    
    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-summary_date"]

    def __str__(self):
        return (
            f"Daily summary for {self.summary_date} "
            f"({self.run_status})"
        )


class JobEvent(models.Model):
    """
    Stores the history of important events during a job's lifecycle.
    """

    class EventType(models.TextChoices):
        CREATED = "CREATED", "Created"
        PROCESSING = "PROCESSING", "Processing"
        PROGRESS = "PROGRESS", "Progress Updated"
        RETRYING = "RETRYING", "Retrying"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.CASCADE,
        related_name="events",
    )

    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
    )

    message = models.CharField(max_length=255)

    # Optional extra details, such as progress percentage or error type.
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["job", "-created_at"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]

    def __str__(self):
        return f"Job #{self.job_id}: {self.event_type}"


class Notification(models.Model):
    """
    Persistent notifications belonging to individual users.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )

    event = models.ForeignKey(
        "jobs.JobEvent",
        on_delete=models.SET_NULL,
        related_name="notifications",
        null=True,
        blank=True,
    )

    title = models.CharField(max_length=150)

    message = models.CharField(max_length=255)

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} - User #{self.user_id}"


class JobProgressEvent(models.Model):
    """
    Persistent history of job progress updates.

    Sequence numbers allow clients to detect missing events.
    """

    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.CASCADE,
        related_name="progress_events",
    )

    sequence = models.PositiveBigIntegerField()

    event = models.CharField(max_length=50)

    status = models.CharField(max_length=50)

    progress = models.PositiveSmallIntegerField(default=0)

    message = models.CharField(
        max_length=255,
        blank = True
    )

    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "sequence"],
                name = "unique_job_progess_sequence",
            ),
        ]
        indexes = [
            models.Index(
                fields=["job", "sequence"],
                name = "job_progress_seq_idx",
            ),
        ]

    def __str__(self):
        return (
            f"Job {self.job_id} - "
            f"Event { self.sequence }: {self.event}"
        )
    



