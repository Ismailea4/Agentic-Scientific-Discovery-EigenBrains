"""Example Server-Sent Events endpoint used to validate the streaming pipeline.

Emits a small, finite heartbeat stream — challenge code replaces or extends
this with real streaming (e.g. provider token streams) later.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ...core.logging import log_event
from ..sse import SSE_HEADERS, format_sse

router = APIRouter(tags=["stream"])

HEARTBEAT_TICKS = 5
HEARTBEAT_INTERVAL_SECONDS = 1.0


async def heartbeat_events() -> AsyncIterator[str]:
    log_event("sse.connected", route="/api/stream/heartbeat", sse_event_type="heartbeat")
    try:
        for tick in range(HEARTBEAT_TICKS):
            payload = {
                "tick": tick,
                "time": datetime.now(timezone.utc).isoformat(),
            }
            log_event(
                "sse.event",
                level=logging.DEBUG,
                route="/api/stream/heartbeat",
                sse_event_type="heartbeat",
            )
            yield format_sse("heartbeat", payload)
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
    finally:
        log_event("sse.disconnected", route="/api/stream/heartbeat", sse_event_type="heartbeat")


@router.get("/stream/heartbeat")
async def heartbeat() -> StreamingResponse:
    return StreamingResponse(
        heartbeat_events(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
