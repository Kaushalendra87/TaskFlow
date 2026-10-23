from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler for consistent error responses.

    Ensures all error responses have a consistent structure:
    {
        "detail": "Human-readable error message",
        "code": "error_code"
    }
    """
    # Call DRF's default exception handler first
    response = drf_exception_handler(exc, context)

    if response is not None:
        # Standardize the response format
        if isinstance(response.data, dict):
            # Already has the right structure with detail and code
            if "detail" in response.data and "code" in response.data:
                return response

            # Handle validation errors (field-specific)
            if any(
                isinstance(v, list) and v and isinstance(v[0], str)
                for v in response.data.values()
            ):
                # This is a field validation error, keep as-is
                return response

            # Handle non-field errors
            if "detail" in response.data:
                error_code = getattr(exc, "default_code", "error")
                return Response(
                    {"detail": response.data["detail"], "code": error_code},
                    status=response.status_code,
                )

            # Generic error response
            return Response(
                {"detail": "An error occurred.", "code": "error"},
                status=response.status_code,
            )

    # For unhandled exceptions (500 errors)
    logger.exception("Unhandled exception: %s", exc)
    return Response(
        {
            "detail": "An internal server error occurred.",
            "code": "internal_error",
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )