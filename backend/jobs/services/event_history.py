from django.db import transaction

from jobs.models import JobEvent, Notification


NOTIFICATION_EVENT_TYPES = {
    JobEvent.EventType.CREATED,
    JobEvent.EventType.COMPLETED,
    JobEvent.EventType.FAILED,
    JobEvent.EventType.CANCELLED,
    JobEvent.EventType.RETRYING,
}


def _notification_title(event_type):
    titles = {
        JobEvent.EventType.CREATED: "Job Created",
        JobEvent.EventType.PROCESSING: "Job Processing",
        JobEvent.EventType.PROGRESS: "Job Progress Updated",
        JobEvent.EventType.RETRYING: "Job Retrying",
        JobEvent.EventType.COMPLETED: "Job Completed",
        JobEvent.EventType.FAILED: "Job Failed",
        JobEvent.EventType.CANCELLED: "Job Cancelled",
    }

    return titles.get(event_type, "Job Update")


@transaction.atomic
def record_job_event(
    *,
    job,
    event_type,
    message,
    metadata=None,
    notify=None,
):
    """
    Record a job event and optionally create a notification.

    Live notification delivery is scheduled only after the
    database transaction successfully commits.
    """

    if metadata is None:
        metadata = {}

    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a dictionary.")

    event = JobEvent.objects.create(
        job=job,
        event_type=event_type,
        message=message,
        metadata=metadata,
    )

    if notify is None:
        notify = event_type in NOTIFICATION_EVENT_TYPES

    if notify:
        notification = Notification.objects.create(
            user=job.user,
            job=job,
            event=event,
            title=_notification_title(event_type),
            message=message,
        )

        notification_id = notification.pk

        def send_after_commit():
            # Import here to avoid unnecessary module-level
            # coupling between the jobs and realtime apps.
            from realtime.services import dispatch_notification

            dispatch_notification(notification_id)

        transaction.on_commit(send_after_commit)

    return event

    