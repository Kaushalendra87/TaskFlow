from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def job_group_name(job_id):
    return f"job_{job_id}"


def send_job_update(job):
    channel_layer = get_channel_layer()

    async_to_sync(
        channel_layer.group_send
    )(
        f"job_{job.id}",
        {
            "type": "job_update",
            "job_id": job.id,
            "status": job.status,
            "progress": job.progress,
            "error_message": job.error_message,
            "cancel_requested": job.cancel_requested,
        },
    )

    