from django.db import transaction
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from jobs.models import Job, JobEvent, Notification
from jobs.notification_serializers import (
    JobEventSerializer,
    NotificationSerializer,
)


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class NotificationListAPIView(APIView):
    """
    GET /api/notifications/

    Return notifications belonging to the authenticated user.

    Optional query parameter:
        ?unread=true
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(
            user=request.user
        ).select_related("job", "event")

        unread_only = request.query_params.get("unread", "").lower()

        if unread_only in {"true", "1", "yes"}:
            notifications = notifications.filter(is_read=False)

        elif unread_only not in {"", "false", "0", "no"}:
            return Response(
                {
                    "detail": (
                        "Invalid 'unread' parameter. "
                        "Use true or false."
                    ),
                    "code": "invalid_parameter",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        paginator = NotificationPagination()
        page = paginator.paginate_queryset(notifications, request, view=self)

        serializer = NotificationSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)

class UnreadNotificationCountAPIView(APIView):
    """
    GET /api/notifications/unread-count/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            user = request.user,
            is_read = False,
        ).count()

        return Response(
            {
                "unread_count": count,
            },
            status=status.HTTP_200_OK,
        )

class MarkNotificationReadAPIView(APIView):
    """
    POST /api/notifications/<notification_id>/read/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id):
        try:
            notification = Notification.objects.get(
                id = notification_id,
                user = request.user,
            )
        except Notification.DoesNotExist:
            return Response(
                {
                    "detail": "Notification not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(
                update_fields=[
                    "is_read",
                    "read_at",
                ]
            )

        return Response(
            NotificationSerializer(notification).data,
            status=status.HTTP_200_OK,
        )

class MarkAllNotificationsReadAPIView(APIView):
    """
    POST /api/notifications/read-all/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        now = timezone.now()

        with transaction.atomic():
            updated_count = Notification.objects.filter(
                user=request.user,
                is_read=False,
            ).update(
                is_read=True,
                read_at=now,
            )

        return Response(
            {
                "message": "All notifications marked as read.",
                "updated_count": updated_count,
            },
            status=status.HTTP_200_OK,
        )

class JobEventHistoryAPIView(APIView):
    """
    GET /api/jobs/<job_id>/events/

    Return event history for a job owned by the authenticated user.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        try:
            job = Job.objects.get(
                id=job_id,
                user=request.user,
            )
        except Job.DoesNotExist:
            # Avoid disclosing whether another user's job exists.
            return Response(
                {"detail": "Job not found.", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        events = JobEvent.objects.filter(
            job=job
        ).order_by("-created_at", "-id")

        paginator = NotificationPagination()
        page = paginator.paginate_queryset(events, request, view=self)

        serializer = JobEventSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)


        