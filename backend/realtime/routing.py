from django.urls import path

from .consumers import JobConsumer, NotificationConsumer

websocket_urlpatterns = [
    path(
        "ws/jobs/<int:job_id>/",
        JobConsumer.as_asgi(),
        name="job-websocket",
    ),
    path(
        "ws/notifications/",
        NotificationConsumer.as_asgi(),
        name="notification-websocket",
    ),
]