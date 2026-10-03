"""Structured application errors and FastAPI exception handlers.

Every error response uses the shape::

    {"error": {"code": str, "message": str, "details": {...}}}

The frontend `ApiError` class mirrors this contract — keep them in sync.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .request_log import note_handled_exception


class AppError(Exception):
    """Base class for errors that should surface as structured API responses."""

    code = "app_error"
    http_status = 500

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status


class NotFoundError(AppError):
    code = "not_found"
    http_status = 404


class ValidationError(AppError):
    code = "validation_error"
    http_status = 422


class ProviderError(AppError):
    code = "provider_error"
    http_status = 502


def error_body(exc: AppError) -> dict[str, Any]:
    return {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        if exc.http_status >= 500:
            note_handled_exception(request.scope, exc)
        return JSONResponse(status_code=exc.http_status, content=error_body(exc))

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "request_validation_error",
                    "message": "Request failed validation.",
                    "details": {"errors": exc.errors()},
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        note_handled_exception(request.scope, exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                    "details": {},
                }
            },
        )
