import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Q, Count
from django.utils import timezone

from jobs.models import JobEvent
from jobs.services.event_history import record_job_event
from jobs.services.progress import update_job_progress
from .models import Job, DailyJobSummary
from .services.job_processor import mark_job_cancelled, process_job
from .services.realtime import send_job_update


logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    max_retries=3,
)
def process_job_task(self, job_id):

    try:

        return process_job(job_id)

    except Exception as exc:
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            logger.info("Skipping task for deleted job %s", job_id)
            return None

        if job.cancel_requested or job.status == Job.Status.CANCELLED:
            return mark_job_cancelled(job)

        if job.status in {
            Job.Status.COMPLETED,
            Job.Status.FAILED,
        }:
            logger.info(
                "Not retrying task for terminal job %s (%s)",
                job_id,
                job.status,
            )
            return job

        if self.request.retries >= self.max_retries:

            job.status = Job.Status.FAILED
            job.error_message = str(exc)

            job.save(
                update_fields=[
                    "status",
                    "error_message",
                ]
            )

            update_job_progress(
                job,
                progress=job.progress,
                status=Job.Status.FAILED,
                event="failed",
                message="Job processing failed.",
                metadata={
                    "error": job.error_message,
                },
            )

            record_job_event(
                job=job,
                event_type=JobEvent.EventType.FAILED,
                message="Your job failed during processing.",
                metadata={
                    "status": job.status,
                    "error": job.error_message,
                },
            )

            send_job_update(job)

            raise

        job.status = Job.Status.RETRYING
        job.error_message = (
            f"Retrying after error: {exc}"
        )
        job.retry_count += 1

        job.save(
            update_fields=[
                "status",
                "error_message",
                "retry_count",
            ]
        )

        update_job_progress(
            job,
            progress=job.progress,
            status=Job.Status.RETRYING,
            event="retrying",
            message="The job failed temporarily and will be retried.",
        )

        record_job_event(
            job=job,
            event_type=JobEvent.EventType.RETRYING,
            message="The job failed temporarily and will be retried.",
            metadata={
                "status": job.status,
            },
        )

        send_job_update(job)

        countdown = 5 * (
            2 ** self.request.retries
        )

        raise self.retry(
            exc=exc,
            countdown=countdown,
        )

@shared_task(
    name="jobs.tasks.generate_daily_job_summary"
)
def generate_daily_job_summary():
    """
    Generate a summary of jobs created on the previous
    calender day in Django's configured timezone.
    """

    #The reporting date is yesterday in the configured
    #Django Timezone

    today = timezone.localdate()
    summary_date = today - timedelta(days=1)

    logger.info(
        "Starting daily job summary for %s",
        summary_date,
    )

    summary = None

    try:
        #Create a summary report if one doesn't exists.
        #If it already exists, reuse it.
        summary, _ = DailyJobSummary.objects.get_or_create(
            summary_date = summary_date,
            defaults={
                "run_status": DailyJobSummary.RunStatus.RUNNING,
                "started_at": timezone.now(),
            },
        )

        #Mark the latest execution as running
        summary.run_status = DailyJobSummary.RunStatus.RUNNING
        summary.error_message = ""
        summary.started_at = timezone.now()
        summary.completed_at = None

        summary.save(
            update_fields=[
                "run_status",
                "error_message",
                "started_at",
                "completed_at",
                "updated_at",
            ]
        )

        #Aggegate jobs created on the reporting date.
        #
        #Django's datefield lookup uses the configured
        #  timezone when interpreting a DateTimeField
        counts = Job.objects.filter(
            created_at__date = summary_date
        ).aggregate(
            total=Count("id"),
            pending=Count(
                "id",
                filter=Q(status=Job.Status.PENDING),
            ),
            processing=Count(
                "id",
                filter=Q(status=Job.Status.PROCESSING),
            ),
            retrying=Count(
                "id",
                filter=Q(status=Job.Status.RETRYING),
            ),
            completed=Count(
                "id",
                filter=Q(status=Job.Status.COMPLETED),
            ),
            failed=Count(
                "id",
                filter=Q(status=Job.Status.FAILED),
            ),
            cancelled=Count(
                "id",
                filter=Q(status=Job.Status.CANCELLED),
            ),
        )

        # Store the results.
        summary.total_jobs = counts["total"]
        summary.pending_jobs = counts["pending"]
        summary.processing_jobs = counts["processing"]
        summary.retrying_jobs = counts["retrying"]
        summary.completed_jobs = counts["completed"]
        summary.failed_jobs = counts["failed"]
        summary.cancelled_jobs = counts["cancelled"]

        summary.run_status = DailyJobSummary.RunStatus.SUCCEEDED
        summary.error_message = ""
        summary.completed_at = timezone.now()

        summary.save(
            update_fields=[
                "total_jobs",
                "pending_jobs",
                "processing_jobs",
                "retrying_jobs",
                "completed_jobs",
                "failed_jobs",
                "cancelled_jobs",
                "run_status",
                "error_message",
                "completed_at",
                "updated_at",
            ]
        )

        logger.info(
            "Daily job summary completed for %s: "
            "total=%s, completed=%s, failed=%s",
            summary_date,
            summary.total_jobs,
            summary.completed_jobs,
            summary.failed_jobs,
        )

        return {
            "summary_date": str(summary_date),
            "total_jobs": summary.total_jobs,
            "completed_jobs": summary.completed_jobs,
            "failed_jobs": summary.failed_jobs,
            "run_status": summary.run_status,
        }

    except Exception as exc:
        logger.exception(
            "Daily job summary failed for %s",
            summary_date
        )

        #Record the failure when a summary record exists.
        if summary is not None:
            try:
                summary.run_status = DailyJobSummary.RunStatus.FAILED
                summary.error_message = str(exc)[:5000]
                summary.completed_at = timezone.now()

                summary.save(
                    update_fields=[
                        "run_status",
                        "error_message",
                        "completed_at",
                        "updated_at",
                    ]
                )

            except Exception:
                logger.exception(
                    "Could not record summary failure for %s",
                    summary_date,
                )

        #Preserve the task failure so Celery can report it.
        raise
    
