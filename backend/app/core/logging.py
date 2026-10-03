"""Stdlib structured logging.

Console output is human-readable. `LOG_FORMAT=json` switches the console to
JSON lines. `LOG_FILE_ENABLED=true` also appends JSON lines to `LOG_FILE_PATH`.
No third-party logging stack.

`log_event` attaches request and execution ids from context, drops empty
values, and redacts secrets before anything is written.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .redaction import mask_secret_text, redact

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_task_id: ContextVar[str | None] = ContextVar("task_id", default=None)
_task_type: ContextVar[str | None] = ContextVar("task_type", default=None)

_EVENTS = logging.getLogger("app.events")
_SKIP = {"timestamp", "log_level", "event_name"}


def safe_error(exc: BaseException) -> str:
    """Short exception text with embedded secrets masked."""

    text = mask_secret_text(str(exc)).replace("\n", " ").strip()
    if len(text) > 300:
        return text[:300] + "…"
    return text or type(exc).__name__


@contextmanager
def bind_execution(
    *,
    task_id: str | None = None,
    task_type: str | None = None,
    trace_id: str | None = None,
) -> Iterator[None]:
    """Attach task identity to log events emitted inside the block."""

    tokens: list[tuple[ContextVar[str | None], Any]] = []
    if task_id is not None:
        tokens.append((_task_id, _task_id.set(task_id)))
    if task_type is not None:
        tokens.append((_task_type, _task_type.set(task_type)))
    if trace_id is not None:
        tokens.append((_trace_id, _trace_id.set(trace_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def current_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None) -> Any:
    return _request_id.set(value)


def reset_request_id(token: Any) -> None:
    _request_id.reset(token)


def log_event(event_name: str, *, level: int = logging.INFO, **fields: Any) -> None:
    """Emit one redacted structured event. `None` and empty containers are omitted."""

    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log_level": logging.getLevelName(level),
        "event_name": event_name,
    }
    context = {
        "request_id": _request_id.get(),
        "trace_id": _trace_id.get(),
        "task_id": _task_id.get(),
        "task_type": _task_type.get(),
    }
    for key, value in {**context, **fields}.items():
        if value is None or value == "" or value == [] or value == ():
            continue
        payload[key] = value
    _EVENTS.log(level, event_name, extra={"event": redact(payload)})


class EventFormatter(logging.Formatter):
    def __init__(self, json_output: bool) -> None:
        super().__init__()
        self.json_output = json_output

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", None)
        if not isinstance(event, dict):
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "log_level": record.levelname,
                "event_name": "log",
                "message": mask_secret_text(record.getMessage()),
            }
        if self.json_output:
            return json.dumps(event, default=str, ensure_ascii=False)
        head = " ".join(
            str(event[key]) for key in ("timestamp", "log_level", "event_name") if event.get(key)
        )
        extras = " ".join(
            f"{key}={_format_value(value)}"
            for key, value in event.items()
            if key not in _SKIP
        )
        return f"{head} {extras}".rstrip()


def _format_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value)
    if isinstance(value, str):
        if any(character.isspace() for character in value):
            return json.dumps(value, ensure_ascii=False)
        return value
    return json.dumps(value, default=str, ensure_ascii=False)


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def configure_logging(
    level: str | None = None,
    log_format: str | None = None,
    file_enabled: bool | None = None,
    file_path: str | Path | None = None,
) -> None:
    """Install console and optional JSONL file handlers on the root logger."""

    level_name = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    chosen = (log_format or os.getenv("LOG_FORMAT", "console")).strip().lower()
    if chosen not in {"console", "json"}:
        chosen = "console"
    enabled = (
        file_enabled
        if file_enabled is not None
        else _as_bool(os.getenv("LOG_FILE_ENABLED"), False)
    )
    path = Path(file_path or os.getenv("LOG_FILE_PATH", "data/logs/app.jsonl"))

    root = logging.getLogger()
    for handler in root.handlers[:]:
        if getattr(handler, "eb_owned", False):
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level_name)

    console = logging.StreamHandler()
    console.setFormatter(EventFormatter(json_output=chosen == "json"))
    console.eb_owned = True  # type: ignore[attr-defined]
    root.addHandler(console)

    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = logging.FileHandler(path, encoding="utf-8")
        handle.setFormatter(EventFormatter(json_output=True))
        handle.eb_owned = True  # type: ignore[attr-defined]
        root.addHandler(handle)
