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
FORBIDDEN = ["probability", "will fail", "confirmed", "guarantee", "definitely", "prevent"]


def _matches(a: str, tool_values: list[float]) -> bool:
    decimals = len(a.partition(".")[2])
    return any(abs(float(a) - t) <= 0.005 * abs(t) or round(t, decimals) == float(a) for t in tool_values)


def check(answer: str, tool_results: list[str]) -> Grounding:
    results = "\n".join(tool_results)
    tool_values = [float(n) for n in re.findall(NUMBER, results)]
    bare = IGNORED.sub(" ", answer)
    # shortcut: a status word is checked against the statuses the tools returned, not the station or pump it names; match per subject when evals show a swap
    returned = set(STATUS.findall(results))
    wrong = [s for s in STATUS.findall(bare) if s not in returned]
    unmatched = [a for a in re.findall(NUMBER, bare) if not _matches(a, tool_values)]
    phrases = [p for p in FORBIDDEN if p in answer.lower()]
    return Grounding(
        passed=not (unmatched or wrong or phrases),
        unmatched_numbers=unmatched + wrong,
        forbidden_phrases=phrases,
    )
