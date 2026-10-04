"""The MCP tool server must import, and every tool an agent is allow-listed for must exist.

Regression for run 3: a syntax error in mcp_server.py left the agents with no
lab tools at all, while every other test still passed.
"""
from pathlib import Path

import yaml

BUNDLE = Path(__file__).resolve().parent.parent / "omnigent" / "lab_pi"


def _server_tools() -> set[str]:
    import asyncio

    from discolab import mcp_server

    return {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}


def test_every_allow_listed_tool_is_served():
    served = _server_tools()
    yamls = list(BUNDLE.glob("tools/mcp/*.yaml")) + list(BUNDLE.glob("agents/*/tools/mcp/*.yaml"))
    assert len(yamls) == 4  # PI, literature, designer, critic
    for y in yamls:
        allowed = set(yaml.safe_load(y.read_text(encoding="utf-8"))["tools"])
        missing = allowed - served
        assert not missing, f"{y.relative_to(BUNDLE)} allow-lists tools the server does not provide: {missing}"


def test_the_server_starts_as_a_module():
    import subprocess
    import sys

    proc = subprocess.run([sys.executable, "-c", "import discolab.mcp_server"], capture_output=True, text=True,
                          cwd=BUNDLE.parent.parent, timeout=60)
    assert proc.returncode == 0, proc.stderr[-800:]
