import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import close_old_connections

from jobs.models import Notification


logger = logging.getLogger(__name__)


def dispatch_notification(notification_id):
    """
    Send an already-persisted notification to the owner's
    WebSocket group.

    This function is safe to call after a database commit.
    The REST notification remains stored even if live delivery fails.
    """

    try:
        close_old_connections()

        notification = (
            Notification.objects
            .select_related("user", "job", "event")
            .get(id=notification_id)
        )

        channel_layer = get_channel_layer()

        if channel_layer is None:
            logger.warning(
                "No channel layer configured; notification %s "
                "was stored but not delivered live.",
                notification_id,
            )
            return

        unread_count = Notification.objects.filter(
            user_id=notification.user_id,
            is_read=False,
        ).count()

        payload = {
            "id": notification.id,
            "title": notification.title,
            "message": notification.message,
            "job_id": notification.job_id,
            "event_id": notification.event_id,
            "is_read": notification.is_read,
            "created_at": notification.created_at.isoformat(),
        }

        async_to_sync(channel_layer.group_send)(
            f"notifications_user_{notification.user_id}",
            {
                "type": "notification.message",
                "notification": payload,
                "unread_count": unread_count,
            },
        )

    except Notification.DoesNotExist:
        logger.warning(
            "Notification %s no longer exists.",
            notification_id,
        )

    except Exception:
        # A Redis or delivery failure must not undo a notification
        # that has already been saved in PostgreSQL.
        logger.exception(
            "Live delivery failed for notification %s.",
            notification_id,
        )

    finally:
        close_old_connections()