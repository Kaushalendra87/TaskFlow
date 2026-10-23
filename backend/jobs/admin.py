from django.contrib import admin
from jobs.models import Job, DailyJobSummary
# Register your models here.

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display =[
        "id",
        "user",
        "status",
        "progress",
        "created_at",
        "completed_at",
    ]

    list_filter = [
        "status",
        "created_at",
    ]

    search_fields = [
        "user__username",
        "user__email",
    ]

@admin.register(DailyJobSummary)
class DailyJobSummaryAdmin(admin.ModelAdmin):
    list_display = (
        "summary_date",
        "total_jobs",
        "completed_jobs",
        "failed_jobs",
        "run_status",
        "started_at",
        "completed_at",
    )

    list_filter = (
        "run_status",
        "summary_date",
    )

    search_fields = (
        "error_message",
    )

    readonly_fields = (
        "summary_date",
        "total_jobs",
        "pending_jobs",
        "processing_jobs",
        "retrying_jobs",
        "completed_jobs",
        "failed_jobs",
        "cancelled_jobs",
        "run_status",
        "error_message",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    )

    ordering = ("-summary_date",)


    