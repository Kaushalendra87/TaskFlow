from django.urls import path

from jobs.views import (
    JobCancelView,
    JobListCreateView,
    JobDetailView,
)

from jobs.summary_views import (
    JobSummaryAPIView,
    DailyJobSummaryAPIView,
)

from jobs.progress_views import JobProgressAPIView, JobProgressHistoryAPIView

from jobs.notification_views import (
    JobEventHistoryAPIView,
    MarkAllNotificationsReadAPIView,
    MarkNotificationReadAPIView,
    NotificationListAPIView,
    UnreadNotificationCountAPIView,
)

urlpatterns =[
    path("", 
        JobListCreateView.as_view(),
        name="job-list-create"
    ),

    path("<int:pk>/",
        JobDetailView.as_view(),
        name="job-detail"
    ),

    path(
        "<int:pk>/cancel/",
        JobCancelView.as_view(),
        name="job-cancel",
    ),

    path(
        "summary/",
        JobSummaryAPIView.as_view(),
        name="job-summary",
    ),

    path(
        "summary/daily/",
        DailyJobSummaryAPIView.as_view(),
        name="daily-job-summary",
    ),

    path(
        "notifications/",
        NotificationListAPIView.as_view(),
        name="notification-list",
    ),
    path(
        "notifications/unread-count/",
        UnreadNotificationCountAPIView.as_view(),
        name="notification-unread-count",
    ),
    path(
        "notifications/read-all/",
        MarkAllNotificationsReadAPIView.as_view(),
        name="notification-read-all",
    ),
    path(
        "notifications/<int:notification_id>/read/",
        MarkNotificationReadAPIView.as_view(),
        name="notification-mark-read",
    ),
    path(
        "<int:job_id>/events/",
        JobEventHistoryAPIView.as_view(),
        name="job-event-history",
    ),

    path(
        "<int:job_id>/progress/",
        JobProgressAPIView.as_view(),
        name="job-progress",
    ),

    path(
        "<int:job_id>/progress-history/",
        JobProgressHistoryAPIView.as_view(),
        name="job-progress-history",
    ),

]