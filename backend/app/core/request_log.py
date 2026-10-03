"""ASGI request logging that does not buffer response bodies.

Streaming responses, including SSE, pass through. Query strings are not
logged: they can carry tokens. Authorization and cookie headers are never
copied onto an event.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .logging import log_event, reset_request_id, safe_error, set_request_id

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_HANDLED_EXCEPTION = "eb_handled_exception"


def note_handled_exception(scope: Scope, exc: BaseException) -> None:
    """Remember a handled error so the request log can describe it once."""

    scope[_HANDLED_EXCEPTION] = {
        "exception_type": type(exc).__name__,
        "error": safe_error(exc),
    }


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _request_id(scope: Scope) -> str:
    supplied = _header(scope, b"x-request-id")
    if supplied and _REQUEST_ID.fullmatch(supplied):
        return supplied
    return uuid.uuid4().hex


class RequestLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(scope)
        method = str(scope.get("method") or "")
        route = str(scope.get("path") or "")
        started = time.perf_counter()
        status: dict[str, int] = {"code": 500}
        token = set_request_id(request_id)
        log_event("request.started", http_method=method, route=route)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = int(message["status"])
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            self._finish(scope, method, route, started, status["code"], exc)
            raise
        else:
            self._finish(scope, method, route, started, status["code"], None)
        finally:
            reset_request_id(token)

    @staticmethod
    def _finish(
        scope: Scope,
        method: str,
        route: str,
        started: float,
        status_code: int,
        exc: BaseException | None,
    ) -> None:
        duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
        failed = exc is not None or status_code >= 500
        fields: dict[str, Any] = {
            "http_method": method,
            "route": route,
            "status_code": status_code,
            "duration_ms": duration_ms,
        }
        noted = scope.get(_HANDLED_EXCEPTION)
        if exc is not None:
            fields["exception_type"] = type(exc).__name__
            fields["error"] = safe_error(exc)
        elif isinstance(noted, dict):
            exception_type = noted.get("exception_type")
            error = noted.get("error")
            if isinstance(exception_type, str) and exception_type:
                fields["exception_type"] = exception_type
            if isinstance(error, str) and error:
                fields["error"] = error
        log_event(
            "request.failed" if failed else "request.completed",
            level=logging.ERROR if failed else logging.INFO,
            **fields,
        )
