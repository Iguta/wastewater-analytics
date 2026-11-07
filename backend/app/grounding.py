"""Deterministic grounding check (ARCHITECTURE.md 8.4): a pure function of the answer and the tool-result JSON."""

from __future__ import annotations

import json
import re
from typing import get_args

from . import data
from .contracts import Grounding, Status

NUMBER = r"(?<![\w.])-?\d+(?:\.\d+)?"
DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T[\d:.]+Z?)?")
# Alert ids (REAL:44371:P1:...:2022-06-01), scenario ids (name:A), case ids (F2-0) and P1-P4 labels carry no claims.
IGNORED = re.compile(r"[A-Z]+(?::[\w-]+){2,}|[a-z0-9_]+:[AB]\b|\bF\d-\d+\b|\bP[1-4]\b")
STATUS = re.compile(rf"\b(?:{'|'.join(get_args(Status))})\b", re.I)
SENTENCE = re.compile(r"(?<!\d)\.(?!\d)|[;\n]")
FORBIDDEN = re.compile(r"\b(?:probability|will fail|confirmed|guarantee|definitely|prevent)\b", re.I)


def _walk(x, key=""):
    """Yield (key, node) for every node of parsed JSON."""
    yield key, x
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _walk(v, k)
    elif isinstance(x, list):
        for v in x:
            yield from _walk(v, key)


def _matches(a: str, tool_values: list[float]) -> bool:
    decimals = len(a.partition(".")[2])
    return any(abs(float(a) - t) <= 0.005 * abs(t) or round(t, decimals) == float(a) for t in tool_values)


def check(answer: str, tool_results: list[str]) -> Grounding:
    """tool_results are the decoded tool texts (JSON)."""
    nodes = [n for r in tool_results for n in _walk(json.loads(r))]
    # Only real quantities ground a number: int/float leaves and numeric strings that are not ids.
    tool_values = [
        abs(float(v))
        for k, v in nodes
        if isinstance(v, (int, float)) and not isinstance(v, bool)
        or isinstance(v, str) and re.fullmatch(NUMBER, v) and not k.endswith("id")
    ]  # fmt: skip
    returned = {str(v).upper() for _, v in nodes if isinstance(v, str)} & set(get_args(Status))
    pump_status: dict[str, set[str]] = {}
    for _, v in nodes:
        if isinstance(v, dict) and "pump_id" in v and "status" in v:
            pump_status.setdefault(v["pump_id"], set()).add(v["status"])
    stations = {v for k, v in nodes if k == "station_id"}
    raw = "\n".join(tool_results)
    bare = IGNORED.sub(" ", answer)
    bad_dates = [d for d in DATE.findall(bare) if d[:10] not in raw]
    bare = DATE.sub(" ", bare)
    bare = re.sub(
        r"\b(?:%s)\b" % "|".join(data.STATIONS), lambda m: " " if m.group() in stations else m.group(), bare
    )
    wrong = []
    for m in STATUS.finditer(answer):
        # A status word must match the pump it names (the last P1-P4 earlier in the same sentence), else any returned status.
        named = re.findall(r"\bP[1-4]\b", SENTENCE.split(answer[: m.start()])[-1])
        allowed = pump_status.get(named[-1], returned) if named else returned
        if m.group().upper() not in allowed:
            wrong.append(m.group())
    unmatched = [
        a
        for a in re.findall(NUMBER, re.sub(r"(?<=\d),(?=\d{3}\b)", "", bare))
        if not _matches(a.lstrip("-"), tool_values)
    ]
    phrases = [p.lower() for p in FORBIDDEN.findall(answer)]
    return Grounding(
        passed=not (bad_dates or unmatched or wrong or phrases),
        unmatched_numbers=bad_dates + unmatched + wrong,
        forbidden_phrases=phrases,
    )
