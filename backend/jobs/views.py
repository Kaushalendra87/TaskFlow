from django.db.models import Q
from django.db import transaction

from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated


from jobs.models import Job, JobEvent
from jobs.serializers import JobSerializer
from jobs.tasks import process_job_task
from jobs.services.realtime import send_job_update
from jobs.services.event_history import record_job_event
from jobs.pagination import JobPagination

class JobListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [
        MultiPartParser, 
        FormParser
    ]

    def get(self, request):
        #Step 1: Retrieve only the jobs owned by the logged-in user.
        queryset = Job.objects.filter(
            user = request.user
        )

        #Step 2: Filter by status.
        job_status = request.query_params.get("status")

        if job_status:
            allowed_statuses = Job.Status.values

            if job_status not in allowed_statuses:
                return Response(
                    {
                        "detail": "Invalid status.",
                        "code": "invalid_status",
                        "allowed_statuses": list(allowed_statuses),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            queryset = queryset.filter(status=job_status)

        #Step 3: Search by filename or error message.
        search_query = request.query_params.get("search", "").strip()

        if search_query:
            queryset = queryset.filter(
                Q(file__icontains = search_query)
                | Q(error_message__icontains = search_query)
            )

        #Step 4: Apply supported ordering
        ordering = request.query_params.get(
            "ordering",
            "-created_at",
        )

        allowed_ordering_fields = {
            "created_at",
            "-created_at",
            "completed_at",
            "-completed_at",
            "status",
            "-status",
            "progress",
            "-progress",
            "id",
            "-id",
        }

        if ordering not in allowed_ordering_fields:
            return Response(
                {
                    "detail": "Invalid ordering field.",
                    "code": "invalid_ordering",
                    "allowed_ordering": sorted(
                        allowed_ordering_fields
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = queryset.order_by(ordering, "-id")

        #Step 5: Paginate the filtered and ordered result.
        paginator = JobPagination()

        page = paginator.paginate_queryset(
            queryset,
            request,
            view=self,
        )

        #Step 6: Serialize the current page
        serializer = JobSerializer(
            page,
            many = True,
            context={"request": request},
        )

        return paginator.get_paginated_response(
            serializer.data
        )


    def post(self, request):
        serializer = JobSerializer(data = request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        job = serializer.save(
            user=request.user
        )

        record_job_event(
            job=job,
            event_type=JobEvent.EventType.CREATED,
            message="Your job has been created and queued for processing.",
            metadata={
                "status": job.status,
            },
        )

        task = process_job_task.delay(job.id)

        job.celery_task_id = task.id

        job.save(
            update_fields=[
                "celery_task_id",
            ]
        )

        return Response(
            JobSerializer(job).data,
            status=status.HTTP_201_CREATED
        )

class JobDetailView(APIView):
    permission_classes=[IsAuthenticated]

    def get(self, request,pk):
        try: 
            job = Job.objects.get(
                pk=pk,
                user=request.user,
            )
        except Job.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "Job not found."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = JobSerializer(job)

        return Response(serializer.data)

    def delete(self, request, pk):
        job = get_object_or_404(
            Job.objects.filter(user=request.user),
            pk=pk,
        )

        if job.status != Job.Status.COMPLETED:
            return Response(
                {
                    "detail": "Only completed jobs can be deleted.",
                    "code": "job_not_completed",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_name = job.file.name
        file_storage = job.file.storage
        with transaction.atomic():
            job.delete()
            transaction.on_commit(
                lambda: file_storage.delete(file_name)
            )

        return Response(status=status.HTTP_204_NO_CONTENT)
    
class JobCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        #Users can only access their own jobs.
        job = get_object_or_404(
            Job,
            pk = pk,
            user = request.user,
        )

        terminal_statuses = [
            Job.Status.COMPLETED,
            Job.Status.CANCELLED,
            Job.Status.FAILED,
        ]

        #Reject cancellation of jobs that have already ended.
        if job.status in terminal_statuses:
            return Response(
                {
                    "detail": (
                        f"Cannot cancel a job with status "
                        f"'{job.status}'."
                    ),
                    "code": "invalid_status_transition",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        #Make repeated requests safe and predictable
        if job.cancel_requested:
            return Response(
                {
                    "detail": "Cancellation has already been requested.",
                    "code": "already_cancelled",
                    "job": JobSerializer(job).data,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        #Ask the worker to stop at its next safe checkpoint.
        job.cancel_requested = True
        job.save(update_fields=["cancel_requested"])

        #Inform connected Websocket clients.
        send_job_update(job)

        return Response(
            {
                "detail": "Job cancellation requested.",
                "code": "cancellation_requested",
                "job": JobSerializer(job).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )
