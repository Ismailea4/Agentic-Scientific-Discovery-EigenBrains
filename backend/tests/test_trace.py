import asyncio
import json
from datetime import datetime, timedelta, timezone

from app.ai.types import ModelResponse, TaskType, TokenUsage
from app.capabilities import Capability, CapabilityLease, CapabilityRequirement, evaluate_policy
from app.fallback import FallbackCandidate, FallbackPolicy, resolve_fallback
from app.instrumentation.models import ModelCallMetrics
from app.instrumentation.pricing import PricingTable
from app.instrumentation.recorder import MetricsRecorder
from app.instrumentation.trace import (
    REDACTED,
    ExecutionTraceBuilder,
    sanitize_metadata,
)
from app.optimization import (
    ArchitectureCandidate,
    ArchitectureMetrics,
    select_best,
)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, milliseconds: float) -> None:
        self.now += timedelta(milliseconds=milliseconds)


def test_metadata_redacts_secretish_keys_and_coerces_values():
    cleaned = sanitize_metadata(
        {
            "api_key": "sk-live-secret",
            "session_token": "abc",
            "db_password": "hunter2",
            "client_secret": "xyz",
            "aws_credential": "cred",
            "env": "APP_TOKEN=abc",
            "label": "unit",
            "retries": 3,
        }
    )

    for key in ("api_key", "session_token", "db_password", "client_secret", "aws_credential", "env"):
        assert cleaned[key] == REDACTED
    assert cleaned["label"] == "unit"
    assert cleaned["retries"] == "3"


def test_trace_aggregates_calls_without_copying_call_metadata():
    clock = _Clock()
    builder = ExecutionTraceBuilder("task-1", "generic", clock=clock)
    pricing = PricingTable()
    pricing.register_model("gpt-4o", 0.0025, 0.01)
    recorder = MetricsRecorder(pricing=pricing)
    recorder.add_sink(builder.observe_model_call)

    async def run():
        async with recorder.track_call(
            model="gpt-4o",
            agent="reader",
            task_type=TaskType.GENERIC,
            metadata={"api_key": "super-secret", "purpose": "unit-test"},
        ) as call:
            call.set_response(
                ModelResponse(
                    content="ok",
                    model="gpt-4o",
                    usage=TokenUsage(input_tokens=1000, output_tokens=500),
                )
            )

    asyncio.run(run())
    clock.advance(25)
    decision = evaluate_policy(
        [Capability(name="read")],
        [CapabilityRequirement(capability="read")],
        [],
        [CapabilityLease(capability="read", allowed=True, source="profile")],
        task_scope=None,
    )
    fallback = resolve_fallback(
        [
            FallbackCandidate(
                id="local",
                available=True,
                capabilities=("read",),
                privacy_class="restricted",
                allowed_tasks=("generic",),
            )
        ],
        FallbackPolicy(
            mandatory_capabilities=("read",),
            accepted_privacy_classes=("restricted",),
            task="generic",
            preference_order=("local",),
        ),
    )
    builder.add_policy_decision(decision)
    builder.add_fallback(fallback)
    builder.set_architecture("held")
    builder.set_quality_score(0.5)
    builder.set_risk_score(0.25)
    builder.set_metadata({"env": "APP_TOKEN=abc", "label": "unit"})
    trace = builder.finish()
    payload = trace.to_dict()
    encoded = json.dumps(payload)

    assert payload["task_id"] == "task-1"
    assert payload["task_type"] == "generic"
    assert payload["selected_architecture"] == "held"
    assert payload["agents_used"] == ["reader"]
    assert payload["models_used"] == ["gpt-4o"]
    assert payload["capability_grants"] == ["read"]
    assert payload["input_tokens"] == 1000
    assert payload["output_tokens"] == 500
    assert payload["cost_usd"] == 0.0075
    assert payload["latency_ms"] == 25
    assert payload["quality_score"] == 0.5
    assert payload["risk_score"] == 0.25
    assert payload["fallback_decisions"][0]["selected_id"] == "local"
    assert payload["policy_decisions"][0]["allowed"] is True
    assert payload["policy_decisions"][0]["timestamp"]
    assert payload["metadata"]["cost_complete"] == "True"
    assert payload["metadata"]["env"] == REDACTED
    assert "super-secret" not in encoded
    assert "purpose" not in encoded
    assert payload["started_at"]
    assert payload["ended_at"]


def test_trace_stores_the_optimizer_decision_it_was_given():
    result = select_best(
        [
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
    )
    trace = ExecutionTraceBuilder("task-3", "generic")
    trace.set_architecture(result.selected_id)
    trace.add_optimization(result)
    payload = trace.build().to_dict()

    assert payload["selected_architecture"] == result.selected_id
    assert payload["optimization_decision"]["selected_id"] == result.selected_id
    assert payload["optimization_decision"]["frontier_ids"] == ["careful", "lean"]


def test_unpriced_model_call_leaves_cost_unset():
    builder = ExecutionTraceBuilder("task-2", "generic")
    builder.observe_model_call(
        ModelCallMetrics(
            timestamp="2026-01-01T00:00:00+00:00",
            model_name="unpriced-model",
            agent_name="writer",
            task_type="generic",
            input_tokens=10,
            output_tokens=4,
            latency_ms=3,
            estimated_cost_usd=None,
            success=True,
        )
    )
    trace = builder.finish()

    assert trace.cost_usd is None
    assert trace.metadata["cost_complete"] == "False"
    assert trace.input_tokens == 10


def test_empty_trace_reports_no_token_usage():
    trace = ExecutionTraceBuilder("task-4", "generic").finish()

    assert trace.input_tokens is None
    assert trace.output_tokens is None
    assert trace.cost_usd is None


def test_trace_masks_exact_environment_secret_in_non_secret_field(monkeypatch):
    secret = "opaque-trace-credential"
    monkeypatch.setenv("TRACE_API_TOKEN", secret)
    builder = ExecutionTraceBuilder("task-secret", "generic")
    builder.set_metadata({"label": f"before-{secret}-after"})
    payload = json.dumps(builder.finish().to_dict())

    assert secret not in payload
    assert "[redacted]" in payload
