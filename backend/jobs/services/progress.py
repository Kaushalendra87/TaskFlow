import logging

from django.db import transaction
from django.utils import timezone

from jobs.models import Job, JobProgressEvent
from jobs.services.realtime_updates import publish_job_update, build_job_update, _send_job_update

logger = logging.getLogger(__name__)


def update_job_progress(
    job,
    *,
    progress,
    event="progress",
    message=None,
    status=None,
    extra=None,
    metadata=None,
):
    """
    Atomically update a job and persist a progress event.

    The live WebSocket update is sent only after the database
    transaction commits.

    Args:
        job: Existing Job instance.
        progress: Integer from 0 to 100.
        event: Event name sent to the WebSocket (1-50 chars).
        message: Human-readable description (max 255 chars).
        status: Optional new job status.
        extra: Optional JSON-serializable metadata (legacy parameter).
        metadata: Optional JSON-serializable metadata (preferred parameter).

    Returns:
        The created JobProgressEvent instance.
    """

    if isinstance(progress, bool) or not isinstance(progress, int):
        raise ValueError("Progress must be an integer.")

    if not 0 <= progress <= 100:
        raise ValueError("Progress must be between 0 and 100.")

    if not job.pk:
        raise ValueError("The job must be saved before progress is updated.")

    if not event or len(event) > 50:
        raise ValueError("Event must contain 1 to 50 characters.")

    # Support both `message` and `extra`/`metadata` parameters for backwards compatibility
    if message is not None and len(message) > 255:
        raise ValueError("Message cannot exceed 255 characters.")

    # Use metadata if provided, otherwise fall back to extra for backwards compatibility
    metadata = metadata if metadata is not None else extra
    metadata = metadata or {}

    if not isinstance(metadata, dict):
        raise ValueError("Metadata must be a dictionary.")

    with transaction.atomic():
        # Lock the database row to prevent concurrent progress updates
        # from assigning the same next sequence number.
        locked_job = Job.objects.select_for_update().get(pk=job.pk)

        locked_job.progress = progress

        update_fields = ["progress", "updated_at"]

        if status is not None:
            locked_job.status = status
            update_fields.append("status")

        locked_job.save(update_fields=update_fields)

        # Determine the next sequence number for this job.
        latest_event = (
            JobProgressEvent.objects
            .filter(job=locked_job)
            .order_by("-sequence")
            .first()
        )

        next_sequence = (
            latest_event.sequence + 1
            if latest_event
            else 1
        )

        progress_event = JobProgressEvent.objects.create(
            job=locked_job,
            sequence=next_sequence,
            event=event,
            status=str(locked_job.status),
            progress=progress,
            message=message or "",
            metadata=metadata,
        )

        payload = build_job_update(
            locked_job,
            event=event,
            message=message,
            extra={
                "sequence": progress_event.sequence,
                "progress_event_id": progress_event.pk,
                "metadata": metadata,
            },
        )

        # Use the same job owner's group as Step 27.
        user_id = locked_job.user_id

        if user_id:
            transaction.on_commit(
                lambda uid=user_id, data=payload: _send_job_update(
                    uid,
                    data,
                )
            )

    # Refresh the caller's object so it sees the updated fields.
    job.refresh_from_db()

    return progress_event