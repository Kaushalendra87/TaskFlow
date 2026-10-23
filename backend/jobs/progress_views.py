from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from jobs.models import Job, JobProgressEvent


class JobProgressAPIView(APIView):
    """
    GET /api/jobs/<job_id>/progress/

    Return the latest persisted state of a job owned by the
    authenticated user.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        job = get_object_or_404(
            Job.objects.filter(user=request.user),
            pk=job_id,
        )

        data = {
            "job_id": job.pk,
            "status": job.status,
            "progress": getattr(job, "progress", 0),
            "created_at": (
                job.created_at.isoformat()
                if getattr(job, "created_at", None)
                else None
            ),
            "updated_at": (
                job.updated_at.isoformat()
                if getattr(job, "updated_at", None)
                else None
            ),
        }

        if hasattr(job, "retry_count"):
            data["retry_count"] = job.retry_count

        # Avoid exposing internal exception details or stack traces.
        if hasattr(job, "error_message"):
            data["error_message"] = (
                job.error_message
                if job.status == "FAILED"
                else None
            )

        return Response(data)

class JobProgressHistoryAPIView(APIView):
    """
    Retrieve a job's latest state and its persisted progress events.

    Optional query parameter:
        after_sequence: Return events with a greater sequence number.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        job = get_object_or_404(
            Job.objects.filter(user=request.user),
            pk = job_id,
        )

        after_sequence_raw  = request.query_params.get("after_sequence")

        if after_sequence_raw is None:
            after_sequence = 0
        else:
            try:
                after_sequence = int(after_sequence_raw)
            except(TypeError, ValueError):
                return Response(
                    {
                        "detail": (
                            "after_sequence must be a non-negative integer."
                        ),
                        "code": "invalid_sequence",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if after_sequence < 0 :
                return Response(
                    {
                        "detail": (
                            "after_sequence must be a non negative integer."
                        ),
                        "code": "invalid_sequence",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        events_queryset = JobProgressEvent.objects.filter(
            job = job,
            sequence__gt = after_sequence,
        ).order_by("sequence")

        #Limit the response size to avoid returning an unbounded history.
        events = list(events_queryset[:200])

        latest_sequence = (
            JobProgressEvent.objects
            .filter(job = job)
            .order_by("-sequence")
            .values_list("sequence", flat=True)
            .first()
            or 0
        )

        return Response(
            {
                "job": {
                    "id": job.pk,
                    "status": str(job.status),
                    "progress": job.progress,
                    "latest_sequence": latest_sequence,
                },
                "events": [
                    {
                        "id": event.pk,
                        "sequence": event.sequence,
                        "event": event.event,
                        "status": event.status,
                        "progress": event.progress,
                        "message": event.message,
                        "metadata": event.metadata,
                        "created_at": event.created_at,
                    }
                    for event in events
                ],
                "has_more": (
                    len(events) == 200
                    and events[-1].sequence < latest_sequence
                ),
            }
        )