import asyncio
import json

import pytest

from app.ai.types import ModelResponse, TaskType, TokenUsage
from app.instrumentation.pricing import PricingTable
from app.instrumentation.recorder import MetricsRecorder


def _response(model: str = "gpt-4o", input_tokens: int = 1000, output_tokens: int = 500):
    return ModelResponse(
        content="result",
        model=model,
        usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def test_track_call_records_success_metrics():
    recorder = MetricsRecorder()

    async def run():
        async with recorder.track_call(
            model="gpt-4o",
            agent="test-agent",
            task_type=TaskType.GENERIC,
            metadata={"purpose": "unit-test"},
        ) as call:
            call.set_response(_response())

    asyncio.run(run())

    (record,) = recorder.get_records()
    assert record.model_name == "gpt-4o"
    assert record.agent_name == "test-agent"
    assert record.task_type == "generic"
    assert record.input_tokens == 1000
    assert record.output_tokens == 500
    assert record.latency_ms >= 0
    assert record.estimated_cost_usd is None
    assert record.success is True
    assert record.error is None
    assert record.metadata == {"purpose": "unit-test"}
    assert record.timestamp


def test_registered_price_estimates_cost():
    pricing = PricingTable()
    pricing.register_model("gpt-4o", 0.0025, 0.01)
    recorder = MetricsRecorder(pricing=pricing)

    async def run():
        async with recorder.track_call(
            model="gpt-4o", agent="test-agent", task_type=TaskType.GENERIC
        ) as call:
            call.set_response(_response())

    asyncio.run(run())

    (record,) = recorder.get_records()
    # 1000 in * 0.0025/1k + 500 out * 0.01/1k
    assert record.estimated_cost_usd == pytest.approx(0.0075)


def test_track_call_records_failure_and_reraises():
    recorder = MetricsRecorder()

    async def run():
        async with recorder.track_call(
            model="gpt-4o", agent="test-agent", task_type=TaskType.GENERIC
        ):
            raise RuntimeError("provider exploded")

    with pytest.raises(RuntimeError, match="provider exploded"):
        asyncio.run(run())

    (record,) = recorder.get_records()
    assert record.success is False
    assert record.error == "RuntimeError"
    assert record.estimated_cost_usd is None


def test_unknown_model_yields_no_cost():
    recorder = MetricsRecorder()

    async def run():
        async with recorder.track_call(
            model="some-unpriced-model", agent="a", task_type="generic"
        ) as call:
            call.set_response(_response(model="some-unpriced-model"))

    asyncio.run(run())

    (record,) = recorder.get_records()
    assert record.success is True
    assert record.estimated_cost_usd is None


def test_jsonl_sink_appends_parseable_lines(tmp_path):
    path = tmp_path / "metrics" / "calls.jsonl"
    recorder = MetricsRecorder(jsonl_path=path)

    async def run():
        for _ in range(2):
            async with recorder.track_call(
                model="gpt-4o-mini", agent="a", task_type=TaskType.GENERIC
            ) as call:
                call.set_response(_response(model="gpt-4o-mini"))

    asyncio.run(run())

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert all(row["model_name"] == "gpt-4o-mini" for row in parsed)
    assert all(row["success"] for row in parsed)

    recorder.clear()
    assert recorder.get_records() == []


def test_metrics_metadata_masks_exact_environment_secret(monkeypatch, tmp_path):
    secret = "opaque-credential-value"
    monkeypatch.setenv("EXPERIMENT_API_TOKEN", secret)
    path = tmp_path / "calls.jsonl"
    recorder = MetricsRecorder(jsonl_path=path)

    async def run():
        async with recorder.track_call(
            model="offline-model",
            agent="test-agent",
            task_type="generic",
            metadata={"label": f"prefix-{secret}-suffix"},
        ) as call:
            call.set_response(_response(model="offline-model"))

    asyncio.run(run())
    serialized = path.read_text(encoding="utf-8")
    assert secret not in serialized
    assert secret not in json.dumps(recorder.get_records()[0].to_dict())
    assert "[redacted]" in serialized
