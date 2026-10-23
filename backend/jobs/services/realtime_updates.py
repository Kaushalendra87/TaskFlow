import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import close_old_connections, transaction


logger = logging.getLogger(__name__)


def build_job_update(
    job,
    *,
    event,
    message=None,
    extra=None,
):
    """
    Build a JSON-serializable snapshot of the current job state.

    Only include information that the job owner is allowed to see.
    """

    update = {
        "job_id": job.pk,
        "event": event,
        "status": job.status,
        "progress": getattr(job, "progress", 0),
        "message": message or "",
        "updated_at": (
            job.updated_at.isoformat()
            if getattr(job, "updated_at", None)
            else None
        ),
    }

    # Optional fields supported by some TaskFlow Job models.
    update["retry_count"] = job.retry_count

    if hasattr(job, "created_at"):
        update["created_at"] = (
            job.created_at.isoformat()
            if job.created_at
            else None
        )

    if extra:
        update["extra"] = extra

    return update


def _send_job_update(user_id, payload):
    """
    Send an update to every active WebSocket connection belonging
    to the job owner.

    Redis/channel-layer failures are logged but do not invalidate
    the saved job state.
    """

    try:
        close_old_connections()

        channel_layer = get_channel_layer()

        if channel_layer is None:
            logger.warning(
                "No channel layer configured; job %s update "
                "was not delivered live.",
                payload.get("job_id"),
            )
            return

        async_to_sync(channel_layer.group_send)(
            f"job_updates_user_{user_id}",
            {
                "type": "job.update",
                "data": payload,
            },
        )

    except Exception:
        logger.exception(
            "Failed to broadcast update for job %s.",
            payload.get("job_id"),
        )

    finally:
        close_old_connections()


def publish_job_update(
    job,
    *,
    event,
    message=None,
    extra=None,
):
    """
    Publish a snapshot of the job's current state.

    Call this after saving the job. If inside a database
    transaction, delivery is deferred until the transaction commits.
    """

    if not job.pk:
        raise ValueError(
            "Cannot publish a real-time update for an unsaved job."
        )

    if not getattr(job, "user_id", None):
        raise ValueError(
            "Cannot publish an update for a job without an owner."
        )

    payload = build_job_update(
        job,
        event=event,
        message=message,
        extra=extra,
    )

    user_id = job.user_id

    transaction.on_commit(
        lambda: _send_job_update(user_id, payload)
    )

    return payload