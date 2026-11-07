"""Deterministic grounding check (ARCHITECTURE.md 8.4): a pure function of the answer and the tool-result JSON."""

from __future__ import annotations

import re
from typing import get_args

from . import data
from .contracts import Grounding, Status

NUMBER = r"-?\d+(?:\.\d+)?"
# Alert ids (REAL:44371:P1:...:2022-06-01), scenario ids (name:A), case ids (F2-0), ISO dates and times, station ids, P1-P4.
IGNORED = re.compile(
    rf"[A-Z]+(?::[\w-]+){{2,}}|[a-z0-9_]+:[AB]\b|\bF\d-\d+\b|\d{{4}}-\d{{2}}-\d{{2}}(?:T[\d:.]+Z?)?"
    rf"|\b(?:{'|'.join(data.STATIONS)})\b|\bP[1-4]\b"
)
STATUS = re.compile(rf"\b(?:{'|'.join(get_args(Status))})\b")
PUMP_STATUS = re.compile(r'"pump_id":\s*"(P[1-4])",\s*"status":\s*"([A-Z_]+)"')
SENTENCE = re.compile(r"(?<!\d)\.(?!\d)|[;\n]")
FORBIDDEN = ["probability", "will fail", "confirmed", "guarantee", "definitely", "prevent"]


def _matches(a: str, tool_values: list[float]) -> bool:
    decimals = len(a.partition(".")[2])
    return any(abs(float(a) - t) <= 0.005 * abs(t) or round(t, decimals) == float(a) for t in tool_values)


def check(answer: str, tool_results: list[str]) -> Grounding:
    results = "\n".join(tool_results)
    tool_values = [float(n) for n in re.findall(NUMBER, results)]
    bare = IGNORED.sub(" ", answer)
    returned = set(STATUS.findall(results))
    pump_status: dict[str, set[str]] = {}
    for pump, status in PUMP_STATUS.findall(results):
        pump_status.setdefault(pump, set()).add(status)
    wrong = []
    for m in STATUS.finditer(answer):
        # A status word must match the pump it names (the last P1-P4 earlier in the same sentence), else any returned status.
        named = re.findall(r"\bP[1-4]\b", SENTENCE.split(answer[: m.start()])[-1])
        allowed = pump_status.get(named[-1], returned) if named else returned
        if m.group() not in allowed:
            wrong.append(m.group())
    unmatched = [a for a in re.findall(NUMBER, bare) if not _matches(a, tool_values)]
    phrases = [p for p in FORBIDDEN if p in answer.lower()]
    return Grounding(
        passed=not (unmatched or wrong or phrases),
        unmatched_numbers=unmatched + wrong,
        forbidden_phrases=phrases,
    )
