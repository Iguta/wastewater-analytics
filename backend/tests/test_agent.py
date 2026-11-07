"""agent.ask's result handling with a fake MCP session and a fake tool runner (raw MCP content blocks)."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS

import pytest

from backend import agent

TOOL_TEXT = json.dumps(
    {
        "status": "INVESTIGATE",
        "pumps": [{"pump_id": "P1", "status": "NORMAL"}, {"pump_id": "P2", "status": "INVESTIGATE"}],
    }
)


class FakeRunner:
    def __init__(self, text):
        self.text = text

    async def __aiter__(self):
        use = NS(type="tool_use", name="assess_station", input={})
        yield NS(content=[use, NS(type="text", text=self.text)], stop_reason="tool_use")

    async def generate_tool_call_response(self):
        return {"content": [{"type": "tool_result", "content": [{"type": "text", "text": TOOL_TEXT}]}]}


class FakeSession:
    def __init__(self, *_):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def initialize(self):
        pass

    async def list_tools(self):
        return NS(tools=[])


@asynccontextmanager
async def fake_stdio(_):
    yield None, None


@pytest.fixture
def run(monkeypatch):
    def setup(text):
        runner = NS(beta=NS(messages=NS(tool_runner=lambda **_: FakeRunner(text))))
        monkeypatch.setattr(agent, "stdio_client", fake_stdio)
        monkeypatch.setattr(agent, "ClientSession", FakeSession)
        monkeypatch.setattr(agent, "AsyncAnthropic", lambda: runner)
        return agent.ask("why?", {})

    return setup


@pytest.mark.anyio
async def test_wrong_pump_status_is_withheld(run):
    r = await run("P1 is INVESTIGATE.")
    assert r.withheld and r.answer_markdown is None and r.grounding.unmatched_numbers == ["INVESTIGATE"]
    assert [c.tool for c in r.tool_calls] == ["assess_station"]


@pytest.mark.anyio
async def test_right_pump_status_is_shown(run):
    r = await run("P1 is NORMAL. P2 is INVESTIGATE.")
    assert not r.withheld and r.answer_markdown
