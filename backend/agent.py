"""Grounded agent (ARCHITECTURE.md 8.4): Claude calls our MCP tools over stdio; the answer is shown only if it passes the grounding check."""

from __future__ import annotations

import asyncio
import json
import sys

from anthropic import AsyncAnthropic, BadRequestError
from anthropic.lib.tools.mcp import async_mcp_tool
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from backend.app import grounding
from backend.app.contracts import AskResult, Grounding, ToolCall

MODEL = "claude-sonnet-5-5"
MAX_TOOL_CALLS = 6
TIMEOUT_S = 60
SYSTEM = (
    "You explain read-only lift-station assessments to utility operators. Call the tools to get facts; never answer "
    "from memory. Quote statuses, numbers, units and alert ids exactly as the tools return them, and only those. "
    "Never estimate a missing reading, a failure probability, a failure date or a confirmed cause; say what is "
    "missing instead. Never suggest operating, overriding or resetting equipment or alarms. When results are "
    "SIMULATED or SYNTHETIC, say so. Keep answers under 150 words: what changed, what supports it, what "
    "contradicts it, what to inspect, citing alert ids."
)
SERVER = StdioServerParameters(command=sys.executable, args=["-m", "backend.mcp_server"])


async def ask(question: str, context: dict) -> AskResult:
    """Raises TimeoutError after 60 s; the caller maps it to 504."""
    async with (
        asyncio.timeout(TIMEOUT_S),
        stdio_client(SERVER) as (read, write),
        ClientSession(read, write) as mcp,
    ):
        await mcp.initialize()
        tools = [async_mcp_tool(t, mcp) for t in (await mcp.list_tools()).tools]
        content = f"{question}\nContext: {json.dumps({k: v for k, v in context.items() if v})}"
        fallback_dropped = False
        for extra in ({"fallbacks": "default", "betas": ["server-side-fallback-2026-07-01"]}, {}):
            calls: list[ToolCall] = []
            results: list[str] = []
            text, refused = "", False
            try:
                runner = AsyncAnthropic().beta.messages.tool_runner(
                    model=MODEL, max_tokens=16000, output_config={"effort": "low"}, system=SYSTEM, tools=tools,
                    messages=[{"role": "user", "content": content}], **extra,
                )  # fmt: skip
                async for message in runner:
                    uses = [b for b in message.content if b.type == "tool_use"]
                    if (
                        len(calls) + len(uses) > MAX_TOOL_CALLS
                    ):  # tools run only after this yield, so none of these ran
                        refused = True
                        break
                    if uses:
                        reply = await runner.generate_tool_call_response()  # cached: the runner reuses it
                        for u, r in zip(uses, reply["content"]):
                            calls.append(ToolCall(tool=u.name, args=u.input, ok=not r.get("is_error")))
                            results.append(json.dumps(r["content"]))
                    refused = refused or message.stop_reason == "refusal"
                    text = "".join(b.text for b in message.content if b.type == "text")
                break
            except BadRequestError:
                if not extra:
                    raise
                fallback_dropped = True
        if refused or not calls or not text:
            g = Grounding(passed=False, unmatched_numbers=[], forbidden_phrases=[])
        else:
            g = grounding.check(text, results)
        return AskResult(
            answer_markdown=text if g.passed else None, withheld=not g.passed, tool_calls=calls,
            grounding=g, model=MODEL, fallback_dropped=fallback_dropped,
        )  # fmt: skip
