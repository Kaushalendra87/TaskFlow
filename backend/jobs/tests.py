import tempfile

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from kombu.exceptions import OperationalError

from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from jobs.models import (
    DailyJobSummary,
    Job,
    JobEvent,
    JobProgressEvent,
    Notification,
)
from jobs.services.csv_processing import CSVValidationError, iter_csv_rows
from jobs.services.job_processor import process_job
from jobs.services.progress import JobAlreadyTerminalError, update_job_progress
from jobs.tasks import process_job_task


User = get_user_model()


class JobProcessingTest(TransactionTestCase):
    """
    Covers the Step 20 processing behaviour: the CSV is streamed rather than
    loaded whole, rows are counted up front for progress, intermediate progress
    is saved at ~5% intervals, and the final update is a single completed event.
    """

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        media_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        media_override.enable()
        self.addCleanup(media_override.disable)
        self.addCleanup(self.media_dir.cleanup)

        self.user = User.objects.create_user(
            username="testuser",
            password="password123",
        )
        # APIClient for any API calls (though process_job is called directly)
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def create_job(self, rows=3):
        body = "col1,col2\n" + "".join(
            f"val{index},val{index}\n" for index in range(rows)
        )
        csv_file = SimpleUploadedFile(
            "test.csv",
            body.encode(),
            content_type="text/csv",
        )
        return Job.objects.create(user=self.user, file=csv_file)

    def run_task(self, task_context, job_id):
        process_job_task.run.__func__(task_context, job_id)

    def process_and_capture(self, job):
        """Run process_job, returning the (status, progress) updates published."""
        published = []

        with patch(
            "jobs.services.job_processor.send_job_update",
            new=lambda updated: published.append(
                (updated.status, updated.progress)
            ),
        ):
            with patch(
                "jobs.services.realtime_updates._send_job_update",
                new=lambda user_id, data: published.append(
                    (data.get("status", "unknown"), data.get("progress", 0))
                ),
            ):
                processed_job = process_job(job.id)

        return processed_job, published

    def test_processing_then_successful_completion(self):
        job = self.create_job(rows=3)

        processed_job, published = self.process_and_capture(job)

        # A 3-row file crosses the 5% threshold at 33 and 66 only; the final
        # completed update reports 100.
        self.assertEqual(
            published,
            [
                (Job.Status.PROCESSING, 0),
                (Job.Status.PROCESSING, 33),
                (Job.Status.PROCESSING, 66),
                (Job.Status.COMPLETED, 100),
            ],
        )
        self.assertEqual(processed_job.status, Job.Status.COMPLETED)
        self.assertEqual(processed_job.progress, 100)
        self.assertIsNotNone(processed_job.completed_at)

    def test_progress_updates_are_throttled_and_final_progress_is_sent(self):
        job = self.create_job(rows=100)

        processed_job, published = self.process_and_capture(job)

        checkpoints = [progress for _, progress in published[1:-1]]

        self.assertEqual(published[0], (Job.Status.PROCESSING, 0))
        # 5% steps only: 19 intermediate updates, not one per row.
        self.assertEqual(checkpoints, list(range(5, 100, 5)))
        self.assertLess(len(checkpoints), 100)
        # Intermediate updates never claim 100%; the completed update does.
        self.assertTrue(
            all(
                state == Job.Status.PROCESSING and progress < 100
                for state, progress in published[1:-1]
            )
        )
        self.assertEqual(published[-1], (Job.Status.COMPLETED, 100))
        self.assertEqual(processed_job.progress, 100)

    def test_empty_csv_completes_immediately(self):
        job = self.create_job(rows=0)

        processed_job, published = self.process_and_capture(job)

        self.assertEqual(
            published,
            [
                (Job.Status.PROCESSING, 0),
                (Job.Status.COMPLETED, 100),
            ],
        )
        self.assertEqual(processed_job.status, Job.Status.COMPLETED)
        self.assertEqual(processed_job.progress, 100)

    def test_completed_notification_matches_persisted_full_progress(self):
        job = self.create_job(rows=2)

        with patch("jobs.services.job_processor.send_job_update"):
            with patch("jobs.services.realtime_updates._send_job_update"):
                process_job(job.id)

        job.refresh_from_db()
        notification = Notification.objects.get(
            job=job,
            title="Job Completed",
        )

        self.assertEqual(job.status, Job.Status.COMPLETED)
        self.assertEqual(job.progress, 100)
        self.assertEqual(notification.event.event_type, JobEvent.EventType.COMPLETED)

    def test_row_counting_excludes_the_header(self):
        from jobs.services.job_processor import count_csv_rows

        for rows in (0, 1, 37):
            with self.subTest(rows=rows):
                job = self.create_job(rows=rows)
                self.assertEqual(count_csv_rows(job), rows)

    def test_csv_processing_accepts_utf8_bom_and_crlf(self):
        job = Job.objects.create(
            user=self.user,
            file=SimpleUploadedFile(
                "international.csv",
                b"\xef\xbb\xbfname,city\r\nAsha,Kathmandu\r\n",
                content_type="application/octet-stream",
            ),
        )

        processed_job, _published = self.process_and_capture(job)

        self.assertEqual(processed_job.status, Job.Status.COMPLETED)
        self.assertEqual(processed_job.progress, 100)

    def test_csv_parser_rejects_rows_with_wrong_column_count(self):
        file_obj = SimpleUploadedFile(
            "invalid.csv",
            b"name,city\nAsha,Kathmandu,extra\n",
            content_type="text/csv",
        )

        with self.assertRaisesRegex(CSVValidationError, "CSV row 2"):
            list(iter_csv_rows(file_obj))

    def test_failed_attempt_sets_retrying_and_schedules_retry(self):
        job = self.create_job()
        failure = RuntimeError("Temporary failure")
        retry_signal = RuntimeError("Retry scheduled")
        task_context = SimpleNamespace(
            request=SimpleNamespace(retries=1),
            max_retries=3,
            retry=Mock(side_effect=retry_signal),
        )

        with patch("jobs.tasks.process_job", side_effect=failure):
            with patch("jobs.tasks.send_job_update") as send_update:
                with self.assertRaisesRegex(RuntimeError, "Retry scheduled"):
                    self.run_task(task_context, job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.RETRYING)
        self.assertIn("Temporary failure", job.error_message)
        task_context.retry.assert_called_once_with(exc=failure, countdown=10)
        send_update.assert_called_once()
        self.assertEqual(send_update.call_args.args[0].status, Job.Status.RETRYING)

    def test_final_failure_sets_failed_and_stores_error(self):
        job = self.create_job()
        failure = RuntimeError("Permanent failure")
        task_context = SimpleNamespace(
            request=SimpleNamespace(retries=3),
            max_retries=3,
            retry=Mock(),
        )

        with patch("jobs.tasks.process_job", side_effect=failure):
            with patch("jobs.tasks.send_job_update") as send_update:
                with self.assertRaisesRegex(RuntimeError, "Permanent failure"):
                    self.run_task(task_context, job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.FAILED)
        self.assertEqual(job.error_message, "Permanent failure")
        task_context.retry.assert_not_called()
        send_update.assert_called_once()
        self.assertEqual(send_update.call_args.args[0].status, Job.Status.FAILED)

    def test_cancelled_job_is_not_retried_after_processing_error(self):
        job = self.create_job()
        job.cancel_requested = True
        job.save(update_fields=["cancel_requested"])
        task_context = SimpleNamespace(
            request=SimpleNamespace(retries=1),
            max_retries=3,
            retry=Mock(),
        )

        with patch("jobs.tasks.process_job", side_effect=RuntimeError("Interrupted")):
            with patch("jobs.services.job_processor.send_job_update"):
                self.run_task(task_context, job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.CANCELLED)
        self.assertFalse(task_context.retry.called)
        self.assertTrue(
            JobEvent.objects.filter(
                job=job,
                event_type=JobEvent.EventType.CANCELLED,
            ).exists()
        )

    def test_deleted_job_task_is_ignored(self):
        job = self.create_job()
        job_id = job.id
        job.delete()
        task_context = SimpleNamespace(
            request=SimpleNamespace(retries=1),
            max_retries=3,
            retry=Mock(),
        )

        self.run_task(task_context, job_id)

        task_context.retry.assert_not_called()

    def test_api_exposes_current_job_state_and_error(self):
        job = self.create_job()
        job.status = Job.Status.RETRYING
        job.progress = 50
        job.error_message = "Temporary failure"
        job.save()

        response = self.client.get(reverse("job-detail", kwargs={"pk": job.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Job.Status.RETRYING)
        self.assertEqual(response.data["progress"], 50)
        self.assertEqual(response.data["error_message"], "Temporary failure")


class JobCancellationTest(APITestCase):
    """Covers the Step 21 cancellation behaviour."""

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        media_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        media_override.enable()
        self.addCleanup(media_override.disable)
        self.addCleanup(self.media_dir.cleanup)

        self.owner = User.objects.create_user(
            username="cancelowner",
            email="cancelowner@example.com",
            password="password123",
        )
        self.other_user = User.objects.create_user(
            username="cancelother",
            email="cancelother@example.com",
            password="password123",
        )
        self.client.force_authenticate(user=self.owner)

    def create_job(self, rows=20, status=None):
        body = "col1,col2\n" + "".join(
            f"val{index},val{index}\n" for index in range(rows)
        )
        job = Job.objects.create(
            user=self.owner,
            file=SimpleUploadedFile(
                "cancel.csv",
                body.encode(),
                content_type="text/csv",
            ),
        )
        if status is not None:
            job.status = status
            job.save(update_fields=["status"])
        return job

    def cancel(self, job):
        with patch("jobs.services.job_processor.send_job_update"):
            return self.client.post(
                reverse("job-cancel", kwargs={"pk": job.id})
            )

    def run_processor_quietly(self, job_id):
        """Run process_job without publishing real channel messages."""
        with patch("jobs.services.job_processor.send_job_update"):
            with patch("jobs.services.realtime_updates._send_job_update"):
                return process_job(job_id)

    def test_cancel_pending_job_is_cancelled_immediately(self):
        job = self.create_job()

        response = self.cancel(job)

        job.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["job"]["status"], Job.Status.CANCELLED)
        self.assertTrue(response.data["job"]["cancel_requested"])
        self.assertTrue(job.cancel_requested)
        self.assertEqual(job.status, Job.Status.CANCELLED)

    def test_queued_job_is_cancelled_when_worker_starts(self):
        job = self.create_job(rows=20)
        self.cancel(job)

        self.run_processor_quietly(job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.CANCELLED)
        # It must never have started processing.
        self.assertEqual(job.progress, 0)

    def test_running_job_stops_at_next_checkpoint(self):
        job = self.create_job(rows=20)
        job.status = Job.Status.PROCESSING
        job.save(update_fields=["status"])

        iterator_calls = 0

        def rows_with_midrun_cancel(_file):
            nonlocal iterator_calls
            iterator_calls += 1
            if iterator_calls == 1:
                yield {"col1": "one", "col2": "one"}
                yield {"col1": "two", "col2": "two"}
                return

            yield {"col1": "one", "col2": "one"}
            Job.objects.filter(pk=job.pk).update(cancel_requested=True)
            yield {"col1": "two", "col2": "two"}

        with patch(
            "jobs.services.job_processor.iter_csv_rows",
            side_effect=rows_with_midrun_cancel,
        ):
            self.run_processor_quietly(job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.CANCELLED)
        self.assertEqual(job.progress, 50)

    def test_terminal_jobs_cannot_be_cancelled(self):
        for terminal in (
            Job.Status.COMPLETED,
            Job.Status.CANCELLED,
            Job.Status.FAILED,
        ):
            with self.subTest(status=terminal):
                job = self.create_job(rows=2, status=terminal)

                response = self.cancel(job)

                job.refresh_from_db()
                expected_status = (
                    status.HTTP_200_OK
                    if terminal == Job.Status.CANCELLED
                    else status.HTTP_400_BAD_REQUEST
                )
                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(job.status, terminal)
                self.assertFalse(job.cancel_requested)

    def test_other_users_cannot_cancel_the_job(self):
        job = self.create_job()
        self.client.force_authenticate(user=self.other_user)

        response = self.cancel(job)

        job.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(job.cancel_requested)
        self.assertEqual(job.status, Job.Status.PENDING)

    def test_repeated_cancellation_is_idempotent(self):
        job = self.create_job()

        statuses = [self.cancel(job).status_code for _ in range(3)]

        self.assertEqual(statuses, [status.HTTP_200_OK] * 3)
        job.refresh_from_db()
        self.assertTrue(job.cancel_requested)
        self.assertEqual(job.status, Job.Status.CANCELLED)

    def test_cancel_after_worker_finished_is_rejected(self):
        job = self.create_job(rows=2)
        self.run_processor_quietly(job.id)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.COMPLETED)

        response = self.cancel(job)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.COMPLETED)

    def test_cancelled_status_is_exposed_by_the_api(self):
        job = self.create_job(rows=2)
        self.cancel(job)

        response = self.client.get(
            reverse("job-detail", kwargs={"pk": job.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Job.Status.CANCELLED)
        self.assertTrue(response.data["cancel_requested"])


class JobListQueryTest(APITestCase):
    """Covers the Step 22 list behaviour: pagination, filtering, search, ordering."""

    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        media_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        media_override.enable()
        self.addCleanup(media_override.disable)
        self.addCleanup(self.media_dir.cleanup)

        self.user = User.objects.create_user(
            username="listowner",
            email="listowner@example.com",
            password="password123",
        )
        self.other_user = User.objects.create_user(
            username="listother",
            email="listother@example.com",
            password="password123",
        )
        self.client.force_authenticate(user=self.user)

    def create_job(self, name="list.csv", status=None, error_message=None,
                   progress=0):
        job = Job.objects.create(
            user=self.user,
            file=SimpleUploadedFile(
                name,
                b"col1,col2\nval1,val2\n",
                content_type="text/csv",
            ),
        )
        fields = []
        if status is not None:
            job.status = status
            fields.append("status")
        if error_message is not None:
            job.error_message = error_message
            fields.append("error_message")
        if progress:
            job.progress = progress
            fields.append("progress")
        if fields:
            job.save(update_fields=fields)
        return job

    def list_jobs(self, **params):
        return self.client.get(reverse("job-list-create"), params)

    def test_csv_upload_accepts_bom_and_queues_processing(self):
        uploaded_file = SimpleUploadedFile(
            "customers.CSV",
            b"\xef\xbb\xbfname,city\r\nAsha,Kathmandu\r\n",
            content_type="application/octet-stream",
        )
        with patch(
            "jobs.views.process_job_task.delay",
            return_value=SimpleNamespace(id="celery-task-1"),
        ) as queue_task:
            response = self.client.post(
                reverse("job-list-create"),
                {"file": uploaded_file},
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Job.Status.PENDING)
        self.assertTrue(
            Job.objects.filter(
                pk=response.data["id"],
                user=self.user,
            ).exists()
        )
        queue_task.assert_called_once_with(response.data["id"])

    def test_csv_upload_rejects_malformed_records_without_creating_job(self):
        uploaded_file = SimpleUploadedFile(
            "invalid.csv",
            b"name,city\nAsha,Kathmandu,unexpected\n",
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("job-list-create"),
            {"file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("CSV row 2", str(response.data["file"]))
        self.assertFalse(Job.objects.filter(user=self.user).exists())

    def test_csv_upload_rejects_non_csv_file_names(self):
        uploaded_file = SimpleUploadedFile(
            "customers.xlsx",
            b"not a csv",
            content_type="application/octet-stream",
        )

        response = self.client.post(
            reverse("job-list-create"),
            {"file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Job.objects.filter(user=self.user).exists())

    def test_csv_upload_reports_unavailable_job_queue(self):
        uploaded_file = SimpleUploadedFile(
            "customers.csv",
            b"name,city\nAsha,Kathmandu\n",
            content_type="text/csv",
        )
        with patch(
            "jobs.views.process_job_task.delay",
            side_effect=OperationalError("Redis is unavailable"),
        ):
            response = self.client.post(
                reverse("job-list-create"),
                {"file": uploaded_file},
                format="multipart",
            )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(response.data["code"], "job_queue_unavailable")
        self.assertFalse(Job.objects.filter(user=self.user).exists())

    def test_list_is_paginated_with_a_ten_row_default(self):
        for index in range(25):
            self.create_job(name=f"page_{index:02d}.csv")

        response = self.list_jobs()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data.keys()),
            {"count", "next", "previous", "results"},
        )
        self.assertEqual(response.data["count"], 25)
        self.assertEqual(len(response.data["results"]), 10)

    def test_page_size_is_honoured_and_capped(self):
        for index in range(25):
            self.create_job(name=f"page_{index:02d}.csv")

        small = self.list_jobs(page_size=5)
        capped = self.list_jobs(page_size=5000)

        self.assertEqual(len(small.data["results"]), 5)
        # The cap is 100, so a request for 5000 returns the whole 25-row set.
        self.assertEqual(len(capped.data["results"]), 25)

    def test_page_beyond_the_last_returns_404(self):
        self.create_job()

        response = self.list_jobs(page=999)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_status_filter_returns_only_matching_jobs(self):
        self.create_job(name="a.csv", status=Job.Status.PENDING)
        self.create_job(name="b.csv", status=Job.Status.PROCESSING)
        for index in range(3):
            self.create_job(
                name=f"done_{index}.csv",
                status=Job.Status.COMPLETED,
            )

        response = self.list_jobs(status=Job.Status.COMPLETED)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)
        self.assertTrue(
            all(
                row["status"] == Job.Status.COMPLETED
                for row in response.data["results"]
            )
        )

    def test_unknown_status_is_rejected_with_the_allowlist(self):
        response = self.list_jobs(status="exploded")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            sorted(response.data["allowed_statuses"]),
            sorted(Job.Status.values),
        )

    def test_search_matches_filename_and_error_message(self):
        self.create_job(name="invoice_alpha.csv")
        self.create_job(name="invoice_beta.csv")
        self.create_job(
            name="unrelated.csv",
            status=Job.Status.FAILED,
            error_message="Parser exploded on row 12",
        )
        self.create_job(name="quiet.csv")

        by_name = self.list_jobs(search="invoice")
        by_error = self.list_jobs(search="exploded")
        case_insensitive = self.list_jobs(search="INVOICE")

        self.assertEqual(by_name.data["count"], 2)
        self.assertEqual(by_error.data["count"], 1)
        self.assertEqual(case_insensitive.data["count"], 2)

    def test_search_with_no_match_returns_an_empty_page(self):
        self.create_job(name="invoice_alpha.csv")

        response = self.list_jobs(search="zzz-nothing-zzz")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_ordering_reorders_the_result_set(self):
        for progress in (30, 10, 20):
            self.create_job(name=f"p{progress}.csv", progress=progress)

        ascending = self.list_jobs(ordering="progress")
        descending = self.list_jobs(ordering="-progress")

        self.assertEqual(
            [row["progress"] for row in ascending.data["results"]],
            [10, 20, 30],
        )
        self.assertEqual(
            [row["progress"] for row in descending.data["results"]],
            [30, 20, 10],
        )

    def test_unknown_ordering_field_is_rejected_with_the_allowlist(self):
        response = self.list_jobs(ordering="-user__password")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("allowed_ordering", response.data)

    def test_completed_job_can_be_deleted(self):
        job = self.create_job(
            name="completed-delete.csv",
            status=Job.Status.COMPLETED,
        )
        event = JobEvent.objects.create(
            job=job,
            event_type=JobEvent.EventType.COMPLETED,
            message="Job completed.",
        )
        notification = Notification.objects.create(
            user=self.user,
            job=job,
            event=event,
            title="Job Completed",
            message="Job completed.",
        )
        file_name = job.file.name
        file_storage = job.file.storage

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(
                reverse("job-detail", kwargs={"pk": job.id})
            )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Job.objects.filter(pk=job.pk).exists())
        self.assertFalse(JobEvent.objects.filter(pk=event.pk).exists())
        self.assertFalse(Notification.objects.filter(pk=notification.pk).exists())
        self.assertFalse(file_storage.exists(file_name))

    def test_non_terminal_job_cannot_be_deleted(self):
        job = self.create_job(
            name="pending-delete.csv",
            status=Job.Status.PENDING,
        )

        response = self.client.delete(
            reverse("job-detail", kwargs={"pk": job.id})
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Job.objects.filter(pk=job.pk).exists())

    def test_failed_and_cancelled_jobs_can_be_deleted(self):
        for job_status in (Job.Status.FAILED, Job.Status.CANCELLED):
            with self.subTest(status=job_status):
                job = self.create_job(
                    name=f"{job_status}-delete.csv",
                    status=job_status,
                )
                file_name = job.file.name
                file_storage = job.file.storage

                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.delete(
                        reverse("job-detail", kwargs={"pk": job.id})
                    )

                self.assertEqual(
                    response.status_code,
                    status.HTTP_204_NO_CONTENT,
                )
                self.assertFalse(Job.objects.filter(pk=job.pk).exists())
                self.assertFalse(file_storage.exists(file_name))

    def test_user_cannot_delete_another_users_job(self):
        job = Job.objects.create(
            user=self.other_user,
            file=SimpleUploadedFile(
                "private-completed.csv",
                b"col1\nvalue\n",
                content_type="text/csv",
            ),
            status=Job.Status.COMPLETED,
        )

        response = self.client.delete(
            reverse("job-detail", kwargs={"pk": job.id})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Job.objects.filter(pk=job.pk).exists())

    def test_combined_query_parameters_compose(self):
        for index in range(4):
            self.create_job(
                name=f"combo_report_{index}.csv",
                status=Job.Status.COMPLETED,
                progress=index * 10,
            )
        self.create_job(
            name="combo_report_failed.csv",
            status=Job.Status.FAILED,
            error_message="report generation failed",
        )
        self.create_job(name="combo_other.csv", status=Job.Status.COMPLETED)

        first = self.list_jobs(
            status=Job.Status.COMPLETED,
            search="combo_report",
            ordering="-progress",
            page_size=2,
            page=1,
        )
        second = self.list_jobs(
            status=Job.Status.COMPLETED,
            search="combo_report",
            ordering="-progress",
            page_size=2,
            page=2,
        )

        self.assertEqual(first.data["count"], 4)
        self.assertEqual(
            [row["progress"] for row in first.data["results"]],
            [30, 20],
        )
        self.assertEqual(
            [row["progress"] for row in second.data["results"]],
            [10, 0],
        )

    def test_list_only_shows_the_callers_own_jobs(self):
        for index in range(3):
            self.create_job(name=f"mine_{index}.csv")
        for index in range(7):
            Job.objects.create(
                user=self.other_user,
                file=SimpleUploadedFile(
                    f"theirs_{index}.csv",
                    b"col1,col2\nval1,val2\n",
                    content_type="text/csv",
                ),
            )

        response = self.list_jobs()

        self.assertEqual(response.data["count"], 3)
        self.assertTrue(
            all(
                row["id"] in set(
                    Job.objects.filter(user=self.user)
                    .values_list("id", flat=True)
                )
                for row in response.data["results"]
            )
        )

    def test_search_cannot_cross_the_ownership_boundary(self):
        self.create_job(name="private_report.csv")
        Job.objects.create(
            user=self.other_user,
            file=SimpleUploadedFile(
                "private_report_other.csv",
                b"col1,col2\nval1,val2\n",
                content_type="text/csv",
            ),
        )

        self.client.force_authenticate(user=self.other_user)
        response = self.list_jobs(search="private_report")

        self.assertEqual(response.data["count"], 1)

    def test_list_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.list_jobs()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)



class JobSummaryAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create two users to test data isolation.
        self.user = User.objects.create_user(
            username="taskflow_user",
            email="taskflow_user@example.com",
            password="TestPassword123!",
        )

        self.other_user = User.objects.create_user(
            username="another_user",
            email="another_user@example.com",
            password="TestPassword123!",
        )

        self.staff_user = User.objects.create_user(
            username="taskflow_staff",
            email="taskflow_staff@example.com",
            password="TestPassword123!",
            is_staff=True,
        )

        self.summary_url = "/api/jobs/summary/"
        self.daily_summary_url = "/api/jobs/summary/daily/"

    def create_job(self, user, filename, job_status):
        """
        Create a job with a small uploaded file.

        Adapt this helper if your Job model has additional
        required fields without defaults.
        """
        uploaded_file = SimpleUploadedFile(
            filename,
            b"column1,column2\nvalue1,value2\n",
            content_type="text/csv",
        )

        return Job.objects.create(
            user=user,
            file=uploaded_file,
            status=job_status,
        )

    def test_summary_requires_authentication(self):
        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, 401)

    def test_summary_returns_only_authenticated_users_jobs(self):
        # Jobs belonging to the authenticated user.
        self.create_job(
            self.user,
            "completed.csv",
            Job.Status.COMPLETED,
        )

        self.create_job(
            self.user,
            "pending.csv",
            Job.Status.PENDING,
        )

        # A different user's job must not affect the response.
        self.create_job(
            self.other_user,
            "other_user.csv",
            Job.Status.FAILED,
        )

        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_jobs"], 2)
        self.assertEqual(response.data["pending_jobs"], 1)
        self.assertEqual(response.data["completed_jobs"], 1)
        self.assertEqual(response.data["failed_jobs"], 0)

    def test_summary_returns_zero_counts_when_user_has_no_jobs(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_jobs"], 0)
        self.assertEqual(response.data["pending_jobs"], 0)
        self.assertEqual(response.data["processing_jobs"], 0)
        self.assertEqual(response.data["retrying_jobs"], 0)
        self.assertEqual(response.data["completed_jobs"], 0)
        self.assertEqual(response.data["failed_jobs"], 0)
        self.assertEqual(response.data["cancelled_jobs"], 0)

    def test_daily_summary_is_staff_only(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.daily_summary_url)

        self.assertEqual(response.status_code, 403)

    def test_staff_can_retrieve_daily_summary_by_date(self):
        summary_date = date(2026, 10, 20)

        summary = DailyJobSummary.objects.create(
            summary_date=summary_date,
            total_jobs=10,
            pending_jobs=1,
            processing_jobs=1,
            retrying_jobs=1,
            completed_jobs=5,
            failed_jobs=1,
            cancelled_jobs=1,
            run_status=DailyJobSummary.RunStatus.SUCCEEDED,
        )

        self.client.force_authenticate(user=self.staff_user)

        response = self.client.get(
            self.daily_summary_url,
            {"date": summary_date.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["summary_date"],
            summary_date.isoformat(),
        )
        self.assertEqual(response.data["total_jobs"], 10)
        self.assertEqual(response.data["completed_jobs"], 5)
        self.assertEqual(
            response.data["run_status"],
            DailyJobSummary.RunStatus.SUCCEEDED,
        )

    def test_daily_summary_returns_404_when_missing(self):
        self.client.force_authenticate(user=self.staff_user)

        response = self.client.get(
            self.daily_summary_url,
            {"date": "2020-01-01"},
        )

        self.assertEqual(response.status_code, 404)

    def test_daily_summary_rejects_invalid_date(self):
        self.client.force_authenticate(user=self.staff_user)

        response = self.client.get(
            self.daily_summary_url,
            {"date": "not-a-date"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"],
            "Invalid date. Use YYYY-MM-DD.",
        )
        self.assertEqual(
            response.data["code"],
            "invalid_date",
        )


class JobProgressHistoryAPITests(APITestCase):
    """Tests for the job progress history API endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="progress_user",
            email="progress@example.com",
            password="TestPass123!",
        )
        self.other_user = User.objects.create_user(
            username="other_user",
            email="other@example.com",
            password="TestPass123!",
        )
        self.client.force_authenticate(user=self.user)

    def create_job_with_progress(self, rows=3):
        """Create a job and process it to generate progress events."""
        body = "col1,col2\n" + "".join(
            f"val{index},val{index}\n" for index in range(rows)
        )
        csv_file = SimpleUploadedFile(
            "test.csv",
            body.encode(),
            content_type="text/csv",
        )
        job = Job.objects.create(user=self.user, file=csv_file)
        process_job(job.id)
        return job

    def test_first_progress_update_has_sequence_1(self):
        """First progress update should have sequence number 1."""
        job = self.create_job_with_progress(rows=3)

        events = JobProgressEvent.objects.filter(job=job).order_by("sequence")
        self.assertEqual(events.count(), 4)  # processing, 33%, 66%, completed
        self.assertEqual(events.first().sequence, 1)
        self.assertEqual(events.first().event, "processing")

    def test_second_progress_update_has_sequence_2(self):
        """Second progress update should have sequence number 2."""
        job = self.create_job_with_progress(rows=3)

        events = JobProgressEvent.objects.filter(job=job).order_by("sequence")
        self.assertEqual(events[1].sequence, 2)
        self.assertEqual(events[1].event, "progress")

    def test_progress_outside_0_100_rejected(self):
        """Progress values outside 0-100 should be rejected."""
        job = Job.objects.create(user=self.user, file=SimpleUploadedFile(
            "test.csv", b"col1\nval1\n", content_type="text/csv"
        ))

        with self.assertRaises(ValueError):
            update_job_progress(job, progress=-1)

        with self.assertRaises(ValueError):
            update_job_progress(job, progress=101)

        with self.assertRaises(ValueError):
            update_job_progress(job, progress=1.5)

        with self.assertRaises(ValueError):
            update_job_progress(job, progress=True)  # bool is not int

    def test_progress_update_cannot_reopen_cancelled_job(self):
        job = Job.objects.create(
            user=self.user,
            file=SimpleUploadedFile(
                "cancelled.csv",
                b"col1\nvalue\n",
                content_type="text/csv",
            ),
            status=Job.Status.CANCELLED,
            cancel_requested=True,
        )

        with self.assertRaises(JobAlreadyTerminalError):
            update_job_progress(job, progress=25)

        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.CANCELLED)
        self.assertEqual(job.progress, 0)

    def test_negative_after_sequence_returns_400(self):
        """Negative after_sequence should return 400."""
        job = self.create_job_with_progress()

        url = f"/api/jobs/{job.id}/progress-history/?after_sequence=-1"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)
        self.assertIn("after_sequence", response.data["detail"].lower())

    def test_non_numeric_after_sequence_returns_400(self):
        """Non-numeric after_sequence should return 400."""
        job = self.create_job_with_progress()

        url = f"/api/jobs/{job.id}/progress-history/?after_sequence=abc"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)
        self.assertIn("after_sequence", response.data["detail"].lower())

    def test_access_another_users_job_returns_404(self):
        """Accessing another user's job should return 404."""
        job = self.create_job_with_progress()

        self.client.force_authenticate(user=self.other_user)
        url = f"/api/jobs/{job.id}/progress-history/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_query_after_sequence_1_returns_later_events(self):
        """Querying after sequence 1 should return only later events."""
        job = self.create_job_with_progress(rows=3)

        url = f"/api/jobs/{job.id}/progress-history/?after_sequence=1"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        events = response.data["events"]
        # Should exclude sequence 1 (processing), include 2, 3, 4
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["sequence"], 2)
        self.assertEqual(events[1]["sequence"], 3)
        self.assertEqual(events[2]["sequence"], 4)

    def test_transaction_rollback_prevents_persistence(self):
        """If transaction rolls back, neither job update nor progress event should persist."""
        job = Job.objects.create(user=self.user, file=SimpleUploadedFile(
            "test.csv", b"col1\nval1\n", content_type="text/csv"
        ))

        # Verify initial state
        self.assertEqual(JobProgressEvent.objects.filter(job=job).count(), 0)

        # Force a rollback by causing an integrity error
        # We can do this by trying to create a progress event with duplicate sequence
        from django.db import transaction, IntegrityError

        # First, create a valid progress event
        update_job_progress(job, progress=50, event="progress", message="Test")
        self.assertEqual(JobProgressEvent.objects.filter(job=job).count(), 1)

        # Now try to manually create a duplicate sequence in a transaction that will rollback
        try:
            with transaction.atomic():
                JobProgressEvent.objects.create(
                    job=job,
                    sequence=1,  # Duplicate sequence
                    event="test",
                    status="TEST",
                    progress=10,
                    message="test",
                )
        except IntegrityError:
            pass

        # The original event should still exist (the valid one)
        # but no new event should have been created
        self.assertEqual(JobProgressEvent.objects.filter(job=job).count(), 1)

        # Also test that a failed update_job_progress doesn't leave partial state
        # by creating a job that will fail validation
        job2 = Job.objects.create(user=self.user, file=SimpleUploadedFile(
            "test2.csv", b"col1\nval1\n", content_type="text/csv"
        ))
        initial_count = JobProgressEvent.objects.filter(job=job2).count()

        try:
            # This should raise ValueError for invalid progress
            update_job_progress(job2, progress=150, event="progress", message="Test")
        except ValueError:
            pass

        # No progress event should have been created for job2
        self.assertEqual(JobProgressEvent.objects.filter(job=job2).count(), initial_count)
