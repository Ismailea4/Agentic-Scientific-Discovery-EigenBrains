import asyncio
from collections.abc import AsyncIterator, Sequence

import pytest

from app.ai.agent import Agent
from app.ai.provider import AIProvider
from app.ai.types import Message, ModelResponse, TaskType, TokenUsage
from app.instrumentation.recorder import MetricsRecorder


class DummyProvider(AIProvider):
    """Minimal test double — lives in tests only, never in production code."""

    @property
    def name(self) -> str:
        return "dummy-model"

    async def generate(self, messages: Sequence[Message], **kwargs) -> ModelResponse:
        return ModelResponse(
            content="dummy-response",
            model=self.name,
            usage=TokenUsage(input_tokens=3, output_tokens=5),
        )

    def stream(self, messages: Sequence[Message], **kwargs) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            yield "dummy-response"

        return _gen()


class EchoAgent(Agent):
    async def run(self, messages: Sequence[Message]) -> str:
        response = await self._generate(messages)
        return response.content


def test_provider_is_abstract():
    with pytest.raises(TypeError):
        AIProvider()


def test_agent_is_abstract():
    with pytest.raises(TypeError):
        Agent(DummyProvider(), name="nope", task_type=TaskType.GENERIC)


def test_agent_generate_routes_through_instrumentation():
    recorder = MetricsRecorder()
    agent = EchoAgent(
        DummyProvider(),
        name="echo-agent",
        task_type=TaskType.GENERIC,
        recorder=recorder,
    )

    content = asyncio.run(agent.run([Message(role="user", content="hi")]))

    assert content == "dummy-response"
    (record,) = recorder.get_records()
    assert record.agent_name == "echo-agent"
    assert record.model_name == "dummy-model"
    assert record.task_type == "generic"
    assert record.input_tokens == 3
    assert record.output_tokens == 5
    assert record.success is True
    # "dummy-model" has no registered price
    assert record.estimated_cost_usd is None
