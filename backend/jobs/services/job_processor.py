import csv
import time

from django.utils import timezone

from jobs.models import Job, JobEvent
from jobs.services.event_history import record_job_event
from jobs.services.progress import update_job_progress
from jobs.services.realtime import send_job_update


PROGRESS_UPDATE_INTERVAL = 5


def count_csv_rows(job):
    """Count CSV data rows without loading all rows into memory."""
    job.file.open("r")

    try:
        reader = csv.DictReader(job.file)
        return sum(1 for _ in reader)
    finally:
        job.file.close()


def process_csv_row(row):
    """
    Simulate processing one CSV row.

    Replace this with actual business logic later.
    """
    time.sleep(1)


def cancellation_requested(job):
    """
    Read the latest cancellation flag from the database.
    """
    job.refresh_from_db(fields=["cancel_requested"])
    return job.cancel_requested


def mark_job_cancelled(job):
    """Persist cancellation and notify connected WebSocket clients."""
    job.status = Job.Status.CANCELLED
    job.save(update_fields=["status"])

    record_job_event(
        job=job,
        event_type=JobEvent.EventType.CANCELLED,
        message="Your job was cancelled.",
        metadata={
            "status": job.status,
        },
    )

    update_job_progress(
        job,
        progress=job.progress,
        status=Job.Status.CANCELLED,
        event="cancelled",
        message="Job was cancelled.",
    )

    send_job_update(job)

    return job


def process_job(job_id):
    job = Job.objects.get(id=job_id)

    # A user might cancel the job before the worker starts.
    if cancellation_requested(job):
        return mark_job_cancelled(job)

    # Initialize processing state.
    update_job_progress(
        job,
        progress=0,
        status=Job.Status.PROCESSING,
        event="processing",
        message="Job processing started.",
    )

    record_job_event(
        job=job,
        event_type=JobEvent.EventType.PROCESSING,
        message="Job processing has started.",
        metadata={
            "status": job.status,
        },
    )

    send_job_update(job)

    total_rows = count_csv_rows(job)

    # Check again after counting the CSV rows.
    if cancellation_requested(job):
        return mark_job_cancelled(job)

    # Handle an empty CSV or a CSV containing only a header.
    if total_rows == 0:
        if cancellation_requested(job):
            return mark_job_cancelled(job)

        update_job_progress(
            job,
            progress=100,
            status=Job.Status.COMPLETED,
            event="completed",
            message="Job completed successfully.",
        )

        job.completed_at = timezone.now()
        job.save(update_fields=["completed_at"])

        record_job_event(
            job=job,
            event_type=JobEvent.EventType.COMPLETED,
            message="Your job has completed successfully.",
            metadata={
                "status": job.status,
                "progress": job.progress,
            },
        )

        send_job_update(job)

        return job

    next_progress_update = PROGRESS_UPDATE_INTERVAL

    job.file.open("r")

    try:
        reader = csv.DictReader(job.file)

        for index, row in enumerate(reader, start=1):

            # Stop before processing the next row if cancellation
            # was requested.
            if cancellation_requested(job):
                return mark_job_cancelled(job)

            process_csv_row(row)

            # A cancellation may have been requested while the
            # current row was being processed.
            if cancellation_requested(job):
                return mark_job_cancelled(job)

            progress = int((index / total_rows) * 100)

            # Save progress at 5% intervals instead of writing
            # to the database for every row.
            if (
                progress >= next_progress_update
                and progress < 100
            ):
                update_job_progress(
                    job,
                    progress=progress,
                    event="progress",
                    message=f"Job progress updated to {progress}%.",
                    metadata={
                        "progress": progress,
                    },
                )

                record_job_event(
                    job=job,
                    event_type=JobEvent.EventType.PROGRESS,
                    message=f"Job progress updated to {progress}%.",
                    metadata={
                        "progress": progress,
                    },
                    notify=False,
                )

                send_job_update(job)

                while next_progress_update <= progress:
                    next_progress_update += PROGRESS_UPDATE_INTERVAL

    finally:
        job.file.close()

    # Do not mark the job completed if cancellation was requested
    # immediately after the last row.
    if cancellation_requested(job):
        return mark_job_cancelled(job)

    # Successful completion.
    update_job_progress(
        job,
        progress=100,
        status=Job.Status.COMPLETED,
        event="completed",
        message="Your job has completed successfully.",
    )

    # Set completed_at explicitly since update_job_progress doesn't handle it
    job.completed_at = timezone.now()
    job.save(update_fields=["completed_at"])

    record_job_event(
        job=job,
        event_type=JobEvent.EventType.COMPLETED,
        message="Your job has completed successfully.",
        metadata={
            "status": job.status,
            "progress": job.progress,
        },
    )

    send_job_update(job)

    return job