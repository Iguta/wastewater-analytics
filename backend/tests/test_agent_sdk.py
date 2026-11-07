"""The real Claude Agent SDK, its bundled CLI and a real stdio MCP server (fixed output), against a fake Anthropic API.

No real key and no network: the CLI talks to a local server that replays scripted model turns and records every request.
"""

import dataclasses
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from backend import agent

ALERT = "REAL:44371:P1:CAPACITY_DROP:2022-06-01"
GOOD = dict(
    summary="P1 is INVESTIGATE.", what_changed=["Capacity changed -31.2%."], supports=[], contradicts=["P2 is NORMAL."],
    missing=["Cause unknown."], inspect=["Check the impeller."], alert_ids=[ALERT],
)  # fmt: skip
ARGS = {"station_id": "44371", "as_of_utc": "2022-06-03T00:00:00Z"}
STUB = str(Path(__file__).parent / "stub_mcp.py")
requests: list[dict] = []
script: list = []


def sse(blocks):
    events = [("message_start", {"message": {"id": "m", "type": "message", "role": "assistant", "model": "x", "content": [], "usage": {"input_tokens": 1, "output_tokens": 1}}})]  # fmt: skip
    for i, b in enumerate(blocks):
        start = {"type": "text", "text": ""} if b["type"] == "text" else {**b, "input": {}}
        delta = {"type": "text_delta", "text": b.get("text")} if b["type"] == "text" else {"type": "input_json_delta", "partial_json": json.dumps(b["input"])}  # fmt: skip
        events += [("content_block_start", {"index": i, "content_block": start}), ("content_block_delta", {"index": i, "delta": delta}), ("content_block_stop", {"index": i})]  # fmt: skip
    stop = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn"
    events += [
        ("message_delta", {"delta": {"stop_reason": stop}, "usage": {"output_tokens": 1}}),
        ("message_stop", {}),
    ]
    return "".join(f"event: {n}\ndata: {json.dumps({'type': n, **d})}\n\n" for n, d in events).encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        names = [t["name"] for t in body.get("tools", [])]
        if "StructuredOutput" in names:  # the real turn; any other call is a side request
            requests.append(body)
            out = sse(script.pop(0))
        else:
            out = sse([{"type": "text", "text": '{"title": "t"}'}])
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def use(name, inp, id="tu1"):
    return [{"type": "tool_use", "id": id, "name": name, "input": inp}]


def final(**over):
    return use("StructuredOutput", {**GOOD, **over}, "so1")


@pytest.fixture(autouse=True)
def sdk(monkeypatch, tmp_path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-dummy-not-real")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(agent, "ROOT", tmp_path)
    monkeypatch.setattr(agent, "SANDBOX", tmp_path / "cwd")
    agent.SESSIONS.clear()
    requests.clear()
    stub = {"dragonfly": {"command": sys.executable, "args": [STUB]}}
    real = agent.query
    monkeypatch.setattr(agent, "query", lambda *, prompt, options: real(prompt=prompt, options=dataclasses.replace(options, mcp_servers=stub)))  # fmt: skip
    yield
    srv.shutdown()


@pytest.mark.anyio
async def test_grounded_answer_and_exact_request_surface():
    script[:] = [use("mcp__dragonfly__assess_station", ARGS), final()]
    r = await agent.ask("Why is P1 flagged?", {"station_id": "44371"})
    assert not r.withheld and r.answer.alert_ids == [ALERT] and "-31.2%" in r.answer_markdown
    assert [(c.tool, c.args, c.ok) for c in r.tool_calls] == [("assess_station", ARGS, True)]
    body = requests[0]
    assert sorted(t["name"] for t in body["tools"] if t["name"] != "DeferredToolPlaceholder") == [
        "StructuredOutput", *(f"mcp__dragonfly__{t}" for t in ("assess_station", "get_evidence", "replay_case"))
    ]  # fmt: skip
    assert agent.SYSTEM in json.dumps(body["system"]) and body["output_config"]["effort"] == "low"
    assert "MEMORY.md" not in json.dumps(body)  # no developer memory in an operator-facing context


@pytest.mark.anyio
async def test_invented_number_is_withheld():
    script[:] = [use("mcp__dragonfly__assess_station", ARGS), final(supports=["Capacity fell 99%."])]
    r = await agent.ask("Why?", {})
    assert r.withheld and r.grounding.unmatched_numbers == ["99"]


@pytest.mark.anyio
async def test_answer_without_a_tool_call_is_withheld():
    script[:] = [final()]
    assert (await agent.ask("Why?", {})).withheld


@pytest.mark.anyio
async def test_built_in_tool_is_denied_not_run():
    script[:] = [
        use("Bash", {"command": "echo pwned"}),
        use("mcp__dragonfly__assess_station", ARGS, "tu2"),
        final(),
    ]
    r = await agent.ask("Why?", {})
    result = [b for m in requests[1]["messages"] for b in m["content"] if isinstance(m["content"], list) and b.get("type") == "tool_result" and b["tool_use_id"] == "tu1"]  # fmt: skip
    assert result and result[0].get("is_error")  # the CLI refused it; nothing ran
    assert [c.tool for c in r.tool_calls] == ["assess_station"] and not r.withheld


@pytest.mark.anyio
async def test_follow_up_resumes_history_but_still_needs_a_tool():
    ctx = {"alert_id": ALERT}
    script[:] = [
        use("mcp__dragonfly__assess_station", ARGS),
        final(),
        use("mcp__dragonfly__assess_station", ARGS),
        final(),
    ]
    await agent.ask("Why?", ctx, "s1")
    second = await agent.ask("And P2?", ctx, "s1")
    assert not second.withheld and len(requests[2]["messages"]) > len(
        requests[0]["messages"]
    )  # history was sent
    script[:] = [final()]
    assert (await agent.ask("And again?", ctx, "s1")).withheld  # answered from history alone
