"""Server-Sent Events formatting helpers shared by streaming routes."""

from __future__ import annotations

import json
from typing import Any


def format_sse(event: str, data: Any) -> str:
    """Serialize one SSE frame: `event: <name>` + JSON `data:` line."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
