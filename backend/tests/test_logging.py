import asyncio
import json
import logging
from collections.abc import Sequence

import pytest

from app.ai.agent import Agent
from app.ai.provider import AIProvider
from app.ai.types import Message, ModelResponse, TaskType, TokenUsage
from app.core.errors import ProviderError
from app.core.logging import bind_execution, configure_logging, log_event
from app.core.redaction import redact
from app.fallback import FallbackCandidate, FallbackPolicy, resolve_fallback
from app.main import create_app
from app.optimization import (
    ArchitectureCandidate,
    ArchitectureMetrics,
    OptimizationWeights,
    select_architecture,
)
from fastapi.testclient import TestClient


def _events(caplog: pytest.LogCaptureFixture) -> list[dict]:
    return [record.event for record in caplog.records if isinstance(getattr(record, "event", None), dict)]


def test_redaction_strips_secret_keys_and_masks_inline_values():
    cleaned = redact(
        {
            "api_key": "sk-live-secretvalue",
            "authorization": "Bearer abcdefghijklmnop",
            "cookie": "session=secret",
            "password": "hunter2",
            "private_key": "abcd",
            "credential": "raw",
            "token": "raw",
            "input_tokens": 12,
            "note": "Authorization: Bearer abcdefghijklmnop",
            "nested": {"aws": "AKIAIOSFODNN7EXAMPLE", "ok": True},
            "prompt": "do not keep",
            "document": "raw user text",
        }
    )

    encoded = json.dumps(cleaned)
    assert cleaned["api_key"] == "[redacted]"
    assert cleaned["authorization"] == "[redacted]"
    assert cleaned["cookie"] == "[redacted]"
    assert cleaned["password"] == "[redacted]"
    assert cleaned["private_key"] == "[redacted]"
    assert cleaned["credential"] == "[redacted]"
    assert cleaned["token"] == "[redacted]"
    assert cleaned["prompt"] == "[redacted]"
    assert cleaned["document"] == "[redacted]"
    assert cleaned["input_tokens"] == 12
    assert cleaned["nested"]["ok"] is True
    assert "sk-live-secretvalue" not in encoded
    assert "abcdefghijklmnop" not in encoded
    assert "AKIAIOSFODNN7EXAMPLE" not in encoded
    assert "Bearer [redacted]" in cleaned["note"]


def test_log_event_redacts_before_the_record_is_emitted(caplog):
    caplog.set_level(logging.INFO, logger="app.events")
    log_event(
        "model.call.completed",
        model_name="example",
        api_key="sk-live-secretvalue",
        input_tokens=4,
        note="Bearer abcdefghijklmnop",
    )

    (event,) = _events(caplog)
    assert event["event_name"] == "model.call.completed"
    assert event["api_key"] == "[redacted]"
    assert event["input_tokens"] == 4
    assert "sk-live-secretvalue" not in caplog.text
    assert "abcdefghijklmnop" not in caplog.text


def test_bind_execution_attaches_task_identity(caplog):
    caplog.set_level(logging.INFO, logger="app.events")
    with bind_execution(task_id="task-7", task_type="generic", trace_id="trace-7"):
        log_event("agent.started", agent_name="reader")

    (event,) = _events(caplog)
    assert event["task_id"] == "task-7"
    assert event["task_type"] == "generic"
    assert event["trace_id"] == "trace-7"
    assert event["agent_name"] == "reader"


def test_json_formatter_and_optional_file(tmp_path):
    path = tmp_path / "app.jsonl"
    configure_logging(level="INFO", log_format="json", file_enabled=True, file_path=path)
    try:
        log_event("request.completed", route="/health", status_code=200, duration_ms=1.5)
        lines = path.read_text(encoding="utf-8").splitlines()
    finally:
        configure_logging(level="INFO", log_format="console", file_enabled=False)

    payload = json.loads(lines[-1])
    assert payload["event_name"] == "request.completed"
    assert payload["route"] == "/health"
    assert payload["status_code"] == 200
    assert "api_key" not in payload


def test_request_logging_omits_headers_and_records_status(caplog):
    caplog.set_level(logging.INFO, logger="app.events")
    client = TestClient(create_app())
    response = client.get(
        "/health",
        headers={"Authorization": "Bearer abcdefghijklmnop", "Cookie": "session=secret"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    names = [event["event_name"] for event in _events(caplog)]
    assert "request.started" in names
    assert "request.completed" in names
    completed = [event for event in _events(caplog) if event["event_name"] == "request.completed"]
    assert completed[-1]["route"] == "/health"
    assert completed[-1]["status_code"] == 200
    assert "abcdefghijklmnop" not in caplog.text
    assert "session=secret" not in caplog.text


def test_one_failed_request_emits_one_request_failed_event(caplog):
    caplog.set_level(logging.DEBUG, logger="app.events")
    app = create_app()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    @app.get("/upstream")
    async def upstream():
        raise ProviderError("upstream failed")

    client = TestClient(app, raise_server_exceptions=False)

    unhandled = client.get("/boom")
    assert unhandled.status_code == 500
    assert unhandled.json()["error"]["code"] == "internal_error"
    boom_failed = [
        event
        for event in _events(caplog)
        if event["event_name"] == "request.failed" and event.get("route") == "/boom"
    ]
    assert len(boom_failed) == 1
    assert boom_failed[0]["status_code"] == 500
    assert boom_failed[0]["exception_type"] == "RuntimeError"
    assert boom_failed[0]["error"] == "boom"
    assert not [
        event
        for event in _events(caplog)
        if event["event_name"] == "request.completed" and event.get("route") == "/boom"
    ]

    caplog.clear()
    handled = client.get("/upstream")
    assert handled.status_code == 502
    assert handled.json()["error"]["code"] == "provider_error"
    assert handled.json()["error"]["message"] == "upstream failed"
    upstream_failed = [
        event
        for event in _events(caplog)
        if event["event_name"] == "request.failed" and event.get("route") == "/upstream"
    ]
    assert len(upstream_failed) == 1
    assert upstream_failed[0]["status_code"] == 502
    assert upstream_failed[0]["exception_type"] == "ProviderError"
    assert upstream_failed[0]["error"] == "upstream failed"


def test_optimizer_and_fallback_emit_auditable_events(caplog):
    caplog.set_level(logging.INFO, logger="app.events")
    candidates = [
        ArchitectureCandidate(
            id="lean",
            name="lean",
            metrics=ArchitectureMetrics(quality=0.5, cost=1.0, latency=10.0, risk=0.25),
        ),
        ArchitectureCandidate(
            id="careful",
            name="careful",
            metrics=ArchitectureMetrics(quality=1.0, cost=2.0, latency=20.0, risk=0.125),
        ),
    ]
    selected = select_architecture(candidates, OptimizationWeights())
    decision = resolve_fallback(
        [
            FallbackCandidate(
                id="primary",
                available=False,
                capabilities=("read",),
                privacy_class="restricted",
                allowed_tasks=("review",),
            ),
            FallbackCandidate(
                id="local",
                available=True,
                capabilities=("read",),
                privacy_class="restricted",
                allowed_tasks=("review",),
            ),
        ],
        FallbackPolicy(
            mandatory_capabilities=("read",),
            accepted_privacy_classes=("restricted",),
            task="review",
            preference_order=("primary", "local"),
        ),
    )

    names = [event["event_name"] for event in _events(caplog)]
    assert "optimizer.started" in names
    assert "optimizer.selected" in names
    assert "fallback.considered" in names
    assert "fallback.rejected" in names
    assert "fallback.selected" in names
    chosen = [event for event in _events(caplog) if event["event_name"] == "optimizer.selected"]
    assert chosen[-1]["selected_candidate"] == selected.selected_id == "careful"
    assert decision.selected_id == "local"


class _SilentProvider(AIProvider):
    @property
    def name(self) -> str:
        return "dummy-model"

    async def generate(self, messages: Sequence[Message], **kwargs) -> ModelResponse:
        return ModelResponse(content="ok", model=self.name, usage=TokenUsage(1, 1))

    def stream(self, messages: Sequence[Message], **kwargs):
        async def _gen():
            yield "ok"

        return _gen()


class _Echo(Agent):
    async def run(self, messages: Sequence[Message]) -> str:
        response = await self._generate(messages)
        return response.content


def test_agent_execute_logs_boundary_without_the_prompt(caplog):
    caplog.set_level(logging.INFO, logger="app.events")
    agent = _Echo(_SilentProvider(), name="echo", task_type=TaskType.GENERIC)
    secret_prompt = "Project Nebula confidential draft"

    asyncio.run(agent.execute([Message(role="user", content=secret_prompt)]))

    names = [event["event_name"] for event in _events(caplog)]
    assert names.count("agent.started") == 1
    assert "model.call.started" in names
    assert "model.call.completed" in names
    assert "agent.completed" in names
    assert secret_prompt not in caplog.text


def test_sse_connection_is_logged(caplog):
    caplog.set_level(logging.INFO, logger="app.events")
    client = TestClient(create_app())
    with client.stream("GET", "/api/stream/heartbeat") as response:
        for chunk in response.iter_text():
            if "event: heartbeat" in chunk:
                break

    names = [event["event_name"] for event in _events(caplog)]
    assert "sse.connected" in names
    connected = [event for event in _events(caplog) if event["event_name"] == "sse.connected"]
    assert connected[0]["sse_event_type"] == "heartbeat"
