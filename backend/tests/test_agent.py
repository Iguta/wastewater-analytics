"""agent.ask with a fake Agent SDK `query` (no network): options, grounding per field, sessions, what-ifs."""

import json
from types import SimpleNamespace as NS

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, ToolResultBlock, ToolUseBlock, UserMessage

from backend import agent

ALERT = "REAL:44371:P1:CAPACITY_DROP:2022-06-01"
TOOL_TEXT = json.dumps(
    {
        "status": "INVESTIGATE",
        "alert_id": ALERT,
        "pumps": [
            {"pump_id": "P1", "status": "INVESTIGATE", "capacity_change_pct": -31.2},
            {"pump_id": "P2", "status": "NORMAL"},
        ],
    }
)
GOOD = dict(
    summary="P1 is INVESTIGATE.", what_changed=["Capacity changed -31.2%."], supports=[], contradicts=["P2 is NORMAL."],
    missing=["Cause unknown."], inspect=["Check the impeller."], alert_ids=[ALERT],
)  # fmt: skip


def script(structured, tools=1, stop_reason="end_turn", subtype="success"):
    """A fake `query` that records its options and prompt, then replays `tools` tool calls and a result."""
    seen = NS(options=[], prompts=[])

    async def fake(*, prompt, options):
        seen.options.append(options)
        seen.prompts.append(prompt)
        for i in range(tools):
            yield AssistantMessage(
                content=[ToolUseBlock(f"t{i}", "mcp__dragonfly__assess_station", {"a": i})], model="m"
            )
            yield UserMessage(content=[ToolResultBlock(f"t{i}", TOOL_TEXT)])
        yield ResultMessage(
            subtype=subtype, duration_ms=0, duration_api_ms=0, is_error=subtype != "success", num_turns=1,
            session_id=f"sdk{len(seen.options)}", stop_reason=stop_reason, structured_output=structured,
        )  # fmt: skip

    return fake, seen


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "ROOT", tmp_path)
    agent.SESSIONS.clear()

    def setup(*a, **k):
        fn, seen = script(*a, **k)
        monkeypatch.setattr(agent, "query", fn)
        return seen

    return setup


@pytest.mark.anyio
async def test_option_surface_is_exactly_three_read_only_tools(fake):
    seen = fake(GOOD)
    r = await agent.ask("why?", {})
    o = seen.options[0]
    assert o.tools == [] and o.permission_mode == "dontAsk" and o.setting_sources == []
    assert o.allowed_tools == [
        f"mcp__dragonfly__{t}" for t in ("assess_station", "get_evidence", "replay_case")
    ]
    assert o.mcp_servers["dragonfly"]["args"] == ["-m", "backend.mcp_server"] and o.model == agent.MODEL
    assert not r.withheld and r.answer.alert_ids == [ALERT] and "-31.2%" in r.answer_markdown
    assert r.tool_calls[0].tool == "assess_station" and r.tool_calls[0].args == {"a": 0}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad",
    [
        {**GOOD, "supports": ["Capacity fell 99%."]},  # a number the tools never returned
        {**GOOD, "summary": "P2 is INVESTIGATE."},  # the wrong status for the named pump
        {**GOOD, "alert_ids": ["REAL:44371:P2:CAPACITY_DROP:2022-06-02"]},  # an id no tool returned
        {**GOOD, "inspect": ["This is confirmed."]},  # a forbidden phrase
    ],
)
async def test_each_field_is_grounded(fake, bad):
    fake(bad)
    r = await agent.ask("why?", {})
    assert r.withheld and r.answer is None and r.answer_markdown is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "kw",
    [
        dict(structured=GOOD, tools=0),  # no tool call this turn
        dict(structured=GOOD, tools=agent.MAX_TOOL_CALLS + 1),
        dict(structured=GOOD, stop_reason="refusal"),
        dict(structured=None, subtype="error_during_execution"),
        dict(structured={"summary": "x"}),  # not the Answer shape
    ],
)
async def test_unsound_runs_are_withheld(fake, kw):
    fake(**kw)
    assert (await agent.ask("why?", {})).withheld


@pytest.mark.anyio
async def test_sessions_resume_and_cap_at_six_turns(fake):
    seen = fake(GOOD)
    ctx = {"alert_id": ALERT}
    for _ in range(agent.MAX_TURNS + 1):
        await agent.ask("why?", ctx, "s1")
    assert [o.resume for o in seen.options] == [None, "sdk1", "sdk2", "sdk3", "sdk4", "sdk5", None]
    await agent.ask("why?", {"alert_id": "REAL:44371:P2:CAPACITY_DROP:2022-06-02"}, "s1")
    assert seen.options[-1].resume is None  # another alert, another conversation
    await agent.ask("why?", ctx)
    assert seen.options[-1].resume is None  # no session id, no history


@pytest.mark.anyio
async def test_follow_up_still_needs_a_tool_call(fake):
    fake(GOOD)
    await agent.ask("why?", {}, "s1")
    fake(GOOD, tools=0)
    assert (await agent.ask("and P2?", {}, "s1")).withheld


@pytest.mark.anyio
@pytest.mark.parametrize(
    "q", ["What if inflow doubles?", "What happens if P1 fails", "Please recalculate with 2x rain"]
)
async def test_what_if_is_logged_not_answered(fake, q):
    seen = fake(GOOD)
    r = await agent.ask(q, {"alert_id": ALERT})
    assert r.answer_markdown == agent.REFUSAL and not r.withheld and r.tool_calls == [] and not seen.options
    row = json.loads((agent.ROOT / "logs" / "questions.jsonl").read_text().splitlines()[-1])
    assert row["question"] == q and row["alert_id"] == ALERT and row["at_utc"].endswith("Z")


def test_what_if_does_not_catch_plain_questions():
    assert not any(agent.WHAT_IF.search(q) for q in ("Why is P1 flagged?", "Which stations need attention?"))
