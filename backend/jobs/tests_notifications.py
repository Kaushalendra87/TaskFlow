from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from jobs.models import Job, JobEvent, Notification
from jobs.services.event_history import record_job_event


User = get_user_model()


class JobNotificationAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="taskflow_user",
            email="taskflow-user@example.com",
            password="TestPassword123!",
        )

        self.other_user = User.objects.create_user(
            username="other_taskflow_user",
            email="other-taskflow-user@example.com",
            password="TestPassword123!",
        )

        self.job = Job.objects.create(
            user=self.user,
            status="PENDING",
        )

        self.client.force_authenticate(user=self.user)

    def test_job_event_creates_notification(self):
        event = record_job_event(
            job=self.job,
            event_type=JobEvent.EventType.COMPLETED,
            message="Your job has completed successfully.",
        )

        self.assertTrue(
            JobEvent.objects.filter(
                id=event.id,
                job=self.job,
            ).exists()
        )

        self.assertTrue(
            Notification.objects.filter(
                user=self.user,
                job=self.job,
                event=event,
                is_read=False,
            ).exists()
        )

    def test_progress_event_does_not_create_notification(self):
        record_job_event(
            job=self.job,
            event_type=JobEvent.EventType.PROGRESS,
            message="Job progress updated to 50%.",
            metadata={"progress": 50},
            notify=False,
        )

        self.assertEqual(
            Notification.objects.filter(user=self.user).count(),
            0,
        )

    def test_user_cannot_see_another_users_notifications(self):
        Notification.objects.create(
            user=self.other_user,
            job=None,
            title="Private notification",
            message="This belongs to another user.",
        )

        response = self.client.get(
            reverse("notification-list")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_unread_notification_count(self):
        Notification.objects.create(
            user=self.user,
            job=self.job,
            title="Job Completed",
            message="Your job has completed.",
        )

        response = self.client.get(
            reverse("notification-unread-count")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unread_count"], 1)

    def test_mark_notification_as_read(self):
        notification = Notification.objects.create(
            user=self.user,
            job=self.job,
            title="Job Completed",
            message="Your job has completed.",
        )

        response = self.client.post(
            reverse(
                "notification-mark-read",
                kwargs={"notification_id": notification.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        notification.refresh_from_db()

        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_mark_already_read_notification_returns_success(self):
        notification = Notification.objects.create(
            user=self.user,
            job=self.job,
            title="Job Completed",
            message="Your job has completed.",
            is_read=True,
        )

        response = self.client.post(
            reverse(
                "notification-mark-read",
                kwargs={"notification_id": notification.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], notification.id)
        self.assertTrue(response.data["is_read"])

    def test_user_cannot_mark_another_users_notification_as_read(self):
        notification = Notification.objects.create(
            user=self.other_user,
            job=None,
            title="Private notification",
            message="This belongs to another user.",
        )

        response = self.client.post(
            reverse(
                "notification-mark-read",
                kwargs={"notification_id": notification.id},
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_user_cannot_view_another_users_job_history(self):
        other_job = Job.objects.create(
            user=self.other_user,
            status="PENDING",
        )

        response = self.client.get(
            reverse(
                "job-event-history",
                kwargs={"job_id": other_job.id},
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_mark_all_notifications_as_read(self):
        Notification.objects.create(
            user=self.user,
            job=self.job,
            title="First notification",
            message="First message.",
        )

        Notification.objects.create(
            user=self.user,
            job=self.job,
            title="Second notification",
            message="Second message.",
        )

        response = self.client.post(
            reverse("notification-read-all")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated_count"], 2)

        self.assertEqual(
            Notification.objects.filter(
                user=self.user,
                is_read=False,
            ).count(),
            0,
        )