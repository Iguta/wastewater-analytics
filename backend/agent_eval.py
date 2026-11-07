"""Agent eval (ARCHITECTURE.md 11.2): 20 fixed questions, a failing one retried once. Gate: at least 19 pass the grounding check."""

from __future__ import annotations

import asyncio
import os
import sys
import tomllib
from pathlib import Path

from backend import agent

PASS_MIN = 19


async def passes(q: dict) -> bool:
    context = {k: v for k, v in q.items() if k != "question"}
    for _ in range(2):
        try:
            r = await agent.ask(q["question"], context)
        except Exception as e:  # a timeout or API error is a failed attempt, not a crashed eval
            print(f"  error: {type(e).__name__}")
            continue
        if r.grounding.passed:
            return True
        print(f"  withheld: {r.grounding.model_dump()}")
    return False


async def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("SKIP: agent-eval (no ANTHROPIC_API_KEY)")
        return 0
    qs = tomllib.loads((Path(__file__).parent / "tests" / "agent_eval.toml").read_text())["q"]
    ok = 0
    for q in qs:
        good = await passes(q)
        ok += good
        print(f"{'PASS' if good else 'FAIL'}: {q['question']}")
    print(f"agent-eval: {ok}/{len(qs)} grounded (gate {PASS_MIN})")
    return 0 if ok >= PASS_MIN else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
