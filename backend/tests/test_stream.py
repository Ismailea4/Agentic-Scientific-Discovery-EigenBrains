import json


def _collect_until_heartbeat(client) -> tuple[str, str]:
    """Read the SSE stream until the first heartbeat frame arrives."""
    content_type = ""
    chunks: list[str] = []
    with client.stream("GET", "/api/stream/heartbeat") as response:
        content_type = response.headers["content-type"]
        for chunk in response.iter_text():
            chunks.append(chunk)
            if "event: heartbeat" in "".join(chunks):
                break
    return content_type, "".join(chunks)


def test_heartbeat_stream_emits_sse_frames(client):
    content_type, text = _collect_until_heartbeat(client)
    assert content_type.startswith("text/event-stream")
    assert "event: heartbeat" in text
    data_lines = [
        line.removeprefix("data: ")
        for line in text.splitlines()
        if line.startswith("data: ")
    ]
    assert data_lines, "expected at least one SSE data line"
    payload = json.loads(data_lines[0])
    assert payload["tick"] == 0
    assert payload["time"]
