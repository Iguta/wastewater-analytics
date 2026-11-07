"""Grounded agent (ARCHITECTURE.md 8.4): the Claude Agent SDK calls our three MCP tools; an answer is shown only if every field passes the grounding check."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from backend.app import grounding
from backend.app.contracts import Answer, AskResult, Grounding, ToolCall

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-sonnet-5-5"  # the one model setting; Haiku 5.5 is swapped here after `make agent-eval`
MAX_TOOL_CALLS = 6
MAX_TURNS = 6
TIMEOUT_S = 60
TOOLS = ["assess_station", "get_evidence", "replay_case"]
SYSTEM = (
    "You explain read-only lift-station assessments to utility operators. Call the tools to get facts; never answer "
    "from memory. On every turn, including follow-ups, call the tools again: earlier turns are never a source of "
    "numbers. Quote statuses, numbers, units and alert ids exactly as the tools return them, and only those. "
    "Never estimate a missing reading, a failure probability, a failure date or a confirmed cause; say what is "
    "missing instead. Never suggest operating, overriding or resetting equipment or alarms. When results are "
    "SIMULATED or SYNTHETIC, say so. You cannot run new analyses. Keep answers under 150 words, as the structured "
    "fields: summary, what changed, what supports it, what contradicts it, what is missing, what to inspect, and "
    "the alert ids cited."
)
WHAT_IF = re.compile(
    r"\bwhat(?:'s| is| would| will)?\s+(?:happens?\s+)?if\b|\brecalculat|\bre-?run\b|\bsimulate\b", re.I
)
REFUSAL = "I can't run new analyses; I've logged this for the reliability team."
# shortcut: sessions live in process memory and are never evicted, move to a TTL store if the server runs long.
SESSIONS: dict[tuple[str, str | None], tuple[str, int]] = {}  # (session_id, alert_id) -> (sdk session, turns)


def render(a: Answer) -> str:
    lines = [a.summary]
    for title, items in (
        ("What changed", a.what_changed), ("Supports", a.supports), ("Contradicts", a.contradicts),
        ("Missing", a.missing), ("Inspect", a.inspect),
    ):  # fmt: skip
        lines += [f"**{title}:** {i}" for i in items]
    return "\n\n".join(lines + ([f"Alerts: {', '.join(a.alert_ids)}"] if a.alert_ids else []))


def check_answer(a: Answer, results: list[str]) -> Grounding:
    """Grounding per field; a cited alert id must appear verbatim in a tool result."""
    raw = "\n".join(results)
    texts = [a.summary, *a.what_changed, *a.supports, *a.contradicts, *a.missing, *a.inspect]
    parts = [grounding.check(t, results) for t in texts]
    return Grounding(
        passed=all(p.passed for p in parts) and all(i in raw for i in a.alert_ids),
        unmatched_numbers=[n for p in parts for n in p.unmatched_numbers] + [i for i in a.alert_ids if i not in raw],
        forbidden_phrases=[f for p in parts for f in p.forbidden_phrases],
    )  # fmt: skip


def log_question(question: str, alert_id: str | None) -> None:
    path = ROOT / "logs" / "questions.jsonl"
    path.parent.mkdir(exist_ok=True)
    row = {
        "question": question,
        "alert_id": alert_id,
        "at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


async def ask(question: str, context: dict, session_id: str | None = None) -> AskResult:
    """Raises TimeoutError after 60 s; the caller maps it to 504."""
    if WHAT_IF.search(question):
        log_question(question, context.get("alert_id"))
        g = Grounding(passed=True, unmatched_numbers=[], forbidden_phrases=[])
        return AskResult(answer_markdown=REFUSAL, withheld=False, tool_calls=[], grounding=g, model=MODEL)
    key = (session_id, context.get("alert_id"))
    sdk_session, turns = SESSIONS.get(key, (None, 0))
    if turns >= MAX_TURNS:  # the 7th question starts a fresh conversation
        sdk_session, turns = None, 0
    options = ClaudeAgentOptions(
        model=MODEL, effort="low", system_prompt=SYSTEM, cwd=ROOT, max_turns=MAX_TOOL_CALLS + 1,
        mcp_servers={"dragonfly": {"command": sys.executable, "args": ["-m", "backend.mcp_server"]}},
        tools=[],  # no built-in tool (shell, files, web) exists for the model
        allowed_tools=[f"mcp__dragonfly__{t}" for t in TOOLS],
        permission_mode="dontAsk",  # anything not allowed is denied, never prompted
        setting_sources=[],
        output_format={"type": "json_schema", "schema": Answer.model_json_schema()},
        resume=sdk_session,
    )  # fmt: skip
    content = f"{question}\nContext: {json.dumps({k: v for k, v in context.items() if v})}"
    calls: list[ToolCall] = []
    results: list[str] = []
    uses: dict[str, ToolUseBlock] = {}
    final: ResultMessage | None = None
    async with asyncio.timeout(TIMEOUT_S):
        async for m in query(prompt=content, options=options):
            blocks = (
                m.content
                if isinstance(m, (AssistantMessage, UserMessage)) and not isinstance(m.content, str)
                else []
            )
            for b in blocks:
                if isinstance(b, ToolUseBlock):
                    uses[b.id] = b
                elif isinstance(b, ToolResultBlock):
                    u = uses[b.tool_use_id]
                    calls.append(
                        ToolCall(
                            tool=u.name.removeprefix("mcp__dragonfly__"), args=u.input, ok=not b.is_error
                        )
                    )
                    c = b.content or ""
                    results.append(c if isinstance(c, str) else "".join(x.get("text", "") for x in c))
            if isinstance(m, ResultMessage):
                final = m
    answer = None
    if final is None or final.subtype != "success" or final.stop_reason == "refusal":
        reason = "refused or errored"
    elif len(calls) > MAX_TOOL_CALLS:
        reason = "over the tool-call cap"
    elif not calls:
        reason = "no tool call"  # a follow-up answered from history is withheld
    else:
        try:
            answer = Answer.model_validate(final.structured_output)
            reason = ""
        except Exception:
            reason = "no structured answer"
    g = (
        Grounding(passed=False, unmatched_numbers=[reason], forbidden_phrases=[])
        if reason
        else check_answer(answer, results)
    )
    if g.passed and session_id and final:
        SESSIONS[key] = (final.session_id, turns + 1)
    return AskResult(
        answer_markdown=render(answer) if g.passed else None, answer=answer if g.passed else None,
        withheld=not g.passed, tool_calls=calls, grounding=g, model=MODEL,
    )  # fmt: skip
