"""The David <-> Dhruv seam (ARCHITECTURE.md 8.1): detector output mapped to the section 7 models.

Real replay only. Scenario and family cases need inject.apply (not built yet) and raise NOT_AVAILABLE.
Inputs are cut at as_of BEFORE features are computed; results are cached on the full instant.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, detect, explain, features, params
from .contracts import (
    ID_PATTERN,
    Evidence,
    Finding,
    LevelPoint,
    Provenance,
    PumpState,
    RainContext,
    RawEvent,
    ReplayResult,
    StationAssessment,
    Thresholds,
    TimelineDay,
    TimelinePump,
    ToolError,
    TraceRow,
    Transition,
)

REAL_MIN = datetime(2022, 3, 16, tzinfo=timezone.utc)
REAL_MAX = datetime(2024, 1, 1, tzinfo=timezone.utc)
RAIN_SOURCE = "Wessex local rainfall gauge (sps-local-rainfall-data)"
WORST_FIRST = ["SOURCE_OFFLINE", "INSUFFICIENT", "PARTIAL", "SUFFICIENT"]
ATTENTION = {"SOURCE_OFFLINE": 0, "INVESTIGATE": 1, "WATCH": 2}
SAFETY = ("SOURCE_SILENT", "HIGH_LEVEL")


class AssessError(Exception):
    def __init__(self, code: str, message: str, allowed: list[str] | None = None):
        super().__init__(message)
        self.error = ToolError(code=code, message=message, allowed=allowed or [])


def scenario_ids() -> list[str]:
    return [f"{p.stem}:{v}" for p in sorted(data.SCENARIOS.glob("*.toml")) for v in "AB"]


def parse_time(s: str | datetime) -> datetime:
    """ISO 8601 with an offset or Z; naive input is rejected."""
    try:
        t = datetime.fromisoformat(s) if isinstance(s, str) else s
    except ValueError:
        t = None
    if t is None or t.tzinfo is None:
        raise AssessError(
            "BAD_TIMESTAMP", f"not an ISO 8601 UTC timestamp: {s!r}; example 2022-06-03T00:00:00Z"
        )
    return t.astimezone(timezone.utc)


def check(station_id: str, scenario_id: str | None, as_of: datetime) -> None:
    if station_id not in data.STATIONS:
        raise AssessError("UNKNOWN_STATION", f"unknown station {station_id!r}", list(data.STATIONS))
    if scenario_id is not None:
        if not re.match(ID_PATTERN, scenario_id) or (
            not scenario_id.startswith("F") and scenario_id not in scenario_ids()
        ):
            raise AssessError("UNKNOWN_SCENARIO", f"unknown scenario {scenario_id!r}", scenario_ids())
        raise AssessError(
            "NOT_AVAILABLE",
            "scenario and family cases need inject.apply (fault injection), which is not built yet; "
            "real replay is available with scenario_id omitted",
        )
    if not REAL_MIN <= as_of <= REAL_MAX:
        raise AssessError(
            "AS_OF_OUT_OF_RANGE",
            f"as_of_utc must be in [{REAL_MIN:%Y-%m-%dT%H:%M:%SZ}, {REAL_MAX:%Y-%m-%dT%H:%M:%SZ}]",
        )


@lru_cache(maxsize=1)
def code_version() -> str:
    root = Path(__file__).resolve().parents[2]
    try:
        git = ["git", "-C", str(root)]
        head = subprocess.run(
            [*git, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
        dirty = subprocess.run([*git, "status", "--porcelain"], capture_output=True, text=True, check=True)
        return head.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _f(x) -> float | None:
    return None if x is None or pd.isna(x) else float(x)


@dataclass
class _Bundle:
    sd: data.StationData  # cut at as_of
    daily: pd.DataFrame  # detect.run output
    rt: list[dict]
    p: params.Params


@lru_cache(maxsize=32)
def _bundle(station_id: str, as_of: datetime) -> _Bundle:
    sd = data.load(station_id)
    end = features.to_naive_utc(as_of)
    sd.events = sd.events[sd.events["ts"] < end]
    sd.level = sd.level[sd.level["ts"] < end]
    sd.rain = sd.rain[sd.rain["ts_hour"] < end]
    p = params.load()
    daily = features.daily_table(sd.events, sd.level, sd.rain, as_of, station_id, sd.quality_counts)
    return _Bundle(sd, detect.run(daily, p), detect.realtime(sd.events, sd.level, as_of, p), p)


def _status_quality(rows: pd.DataFrame, rt_types: set[str]) -> tuple[str, str]:
    """Section 4.10 status and section 4.9 station quality from one day's pump rows plus realtime findings."""
    seen = set(rows["status"]) | ({"WATCH"} if rows["pump_not_running"].any() else set())
    seen |= {"WATCH"} if (rows["station_wide_status"] != "NORMAL").any() else set()
    q = [r.quality for r in rows.itertuples() if not r.standby] or list(rows["quality"])
    quality = max(q, key=WORST_FIRST.index) if q else "INSUFFICIENT"
    if "SENSOR_FAULT" in rt_types and quality == "SUFFICIENT":
        quality = "PARTIAL"
    if "SOURCE_SILENT" in rt_types:
        return "SOURCE_OFFLINE", "SOURCE_OFFLINE"
    if "INVESTIGATE" in seen:
        return "INVESTIGATE", quality
    if "WATCH" in seen or rt_types & {"SENSOR_FAULT", "HIGH_LEVEL"}:
        return "WATCH", quality
    if (
        not rows["quality"].isin(["SUFFICIENT", "PARTIAL"]).any()
        or (rows["status"] == "INSUFFICIENT_EVIDENCE").all()
    ):
        return "INSUFFICIENT_EVIDENCE", quality
    return "NORMAL", quality


def _opened(days: pd.Series, flag: pd.Series) -> date:
    """First day of the run of True that ends on the last day."""
    on = days[flag.to_numpy()]
    d = days.iloc[-1]
    while (d - timedelta(days=1)) in set(on):
        d -= timedelta(days=1)
    return d.date()


def _findings(b: _Bundle, station_id: str, as_of: datetime) -> list[Finding]:
    d = b.daily
    out: list[Finding] = []
    if len(d):
        last = d["day"].max()
        today = d[d["day"] == last]
        wide = d.drop_duplicates("day").sort_values("day")
        for r in today.itertuples():
            if r.status in ("WATCH", "INVESTIGATE") and isinstance(r.incident_id, str):
                opened = date.fromisoformat(r.incident_id.rsplit(":", 1)[1])
                days_open = (last.date() - opened).days + 1
                expected = float(np.exp(r.base_median))
                out.append(
                    _finding(
                        r.incident_id,
                        "CAPACITY_DROP",
                        r.pump_id,
                        r.status,
                        opened,
                        days_open,
                        _f(r.ci),
                        expected,
                        "per hour",
                        _f(r.capacity_change_pct),
                        f"{r.pump_id} pumping capacity {abs(r.capacity_change_pct):.0f}% below its normal for {days_open} days",
                    )
                )
            if r.pump_not_running:
                pump = d[d["pump_id"] == r.pump_id].sort_values("day")
                opened = _opened(pump["day"], pump["pump_not_running"])
                out.append(
                    _finding(
                        f"REAL:{station_id}:{r.pump_id}:PUMP_NOT_RUNNING:{opened}",
                        "PUMP_NOT_RUNNING",
                        r.pump_id,
                        "WATCH",
                        opened,
                        (last.date() - opened).days + 1,
                        0.0,
                        None,
                        "runs",
                        None,
                        f"{r.pump_id} had 0 runs today while a sibling pump ran",
                    )
                )
        if today["station_wide_status"].iloc[0] != "NORMAL":
            opened = _opened(wide["day"], wide["station_wide_status"] != "NORMAL")
            out.append(
                _finding(
                    f"REAL:{station_id}:STATION:STATION_WIDE_CHANGE:{opened}",
                    "STATION_WIDE_CHANGE",
                    None,
                    today["station_wide_status"].iloc[0],
                    opened,
                    (last.date() - opened).days + 1,
                    None,
                    None,
                    "percent",
                    _f(today["station_shared_change_pct"].iloc[0]),
                    "every pump's capacity shifted together",
                )
            )
    for e in b.rt:
        if e["type"] == "HIGH_LEVEL" and e["status"] != "INVESTIGATE":
            continue  # UNKNOWN is reported in missing_evidence
        since = pd.Timestamp(e.get("since") or e.get("at") or features.to_naive_utc(as_of)).tz_localize("UTC")
        sid = f"REAL:{station_id}:STATION:{e['type']}:{since.date()}"
        text = "; ".join(e.get("reasons") or e.get("flags") or [e.get("note", "")])
        out.append(
            _finding(
                sid,
                e["type"],
                None,
                e["status"],
                since.date(),
                (as_of.date() - since.date()).days + 1,
                e.get("peak"),
                e.get("threshold"),
                "m" if e["type"] == "HIGH_LEVEL" else "",
                None,
                f"{e['type']}: {text}",
                since=since.to_pydatetime(),
            )
        )
    # INVESTIGATE by capacity loss (largest first), then by days open (4.11)
    out.sort(
        key=lambda f: (
            ATTENTION[f.status],
            (f.change_pct or 0) if f.status == "INVESTIGATE" else 0,
            -f.days_open,
        )
    )
    for i, f in enumerate(out, 1):
        f.priority = i
    return out


def _finding(
    alert_id, type_, pump, status, opened, days_open, observed, expected, units, change, summary, since=None
):
    return Finding(
        alert_id=alert_id, type=type_, pump_id=pump, status=status, priority=0, opened_on=opened,
        since_utc=since or datetime.combine(opened, time.min, tzinfo=timezone.utc), days_open=days_open, observed=observed, expected=expected,
        units=units, change_pct=change, summary=summary, possible_causes=[],
        inspection=explain.CHECKLISTS[type_],
    )  # fmt: skip


def _pumps(b: _Bundle) -> list[PumpState]:
    d = b.daily
    if d.empty:
        return []
    out = []
    for r in d[d["day"] == d["day"].max()].itertuples():
        status = "WATCH" if r.pump_not_running and r.status == "NORMAL" else r.status
        out.append(
            PumpState(
                pump_id=r.pump_id, status=status, quality=r.quality, ci_today=_f(r.ci),
                ci_baseline=_f(np.exp(r.base_median)), capacity_change_pct=_f(r.capacity_change_pct),
                cusum=float(r.cusum), valid_cycles=int(r.valid_cycles), runs=int(r.runs),
                run_median_s=_f(r.run_median_s), expected_run_s=None,
            )
        )  # fmt: skip
    return out


def _rain(b: _Bundle, as_of: datetime) -> RainContext:
    d, rain = b.daily, b.sd.rain
    today = _f(d["rain_mm"].iloc[-1]) if len(d) else None
    end = features.to_naive_utc(as_of)
    w = rain[rain["ts_hour"] >= end - pd.Timedelta(hours=72)]["mm"]
    return RainContext(
        today_mm=today,
        last_72h_mm=None if len(w) < 72 or w.isna().any() else float(w.sum()),
        source=RAIN_SOURCE,
    )


@lru_cache(maxsize=128)
def assess_station(station_id: str, as_of_utc: datetime, scenario_id: str | None = None) -> StationAssessment:
    as_of = parse_time(as_of_utc)
    check(station_id, scenario_id, as_of)
    b = _bundle(station_id, as_of)
    queue = _findings(b, station_id, as_of)
    pumps = _pumps(b)
    d = b.daily
    rows = d[d["day"] == d["day"].max()] if len(d) else d
    status, quality = (
        _status_quality(rows, {f.type for f in queue})
        if len(rows)
        else ("INSUFFICIENT_EVIDENCE", "INSUFFICIENT")
    )
    missing = [
        f"HIGH_LEVEL check unknown: {e['reason']}"
        for e in b.rt
        if e["type"] == "HIGH_LEVEL" and e["status"] == "UNKNOWN"
    ]
    missing += ["no complete day of pump data before as_of"] * (not len(d))
    missing += [f"{p.pump_id}: evidence {p.quality}" for p in pumps if p.quality != "SUFFICIENT"]
    missing += ["storm outlook: not available for real replay stations"]
    top = queue[0] if queue else None
    pump = next((p for p in pumps if top and p.pump_id == top.pump_id), None)
    order = explain.work_order(top, station_id) if top else None
    return StationAssessment(
        station_id=station_id, display_name=f"Station {station_id}", as_of_utc=as_of, origin="REAL_REPLAY",
        scenario_id=None, status=status, quality=quality, pumps=pumps, queue=queue,
        safety=[f for f in queue if f.type in SAFETY], rain=_rain(b, as_of), storm=None, missing_evidence=missing,
        explanation=explain.explanation(station_id, status, top, pump, missing),
        recommended_action=f"{order.title}. First check: {order.checks[0]}." if order else "No action from the detector.",
        provenance=Provenance(
            source_hash=b.sd.source_hash, scenario_hash=None, model_version=b.p.version,
            code_version=code_version(), signal_ids=b.sd.signal_ids,
        ),
    )  # fmt: skip


def get_evidence(alert_id: str, as_of_utc: datetime) -> Evidence:
    as_of = parse_time(as_of_utc)
    parts = alert_id.rsplit(":", 4)
    if len(parts) != 5 or parts[1] not in data.STATIONS:
        raise AssessError(
            "UNKNOWN_ALERT", f"malformed or unknown alert id {alert_id!r}; use one from assess_station.queue"
        )
    scope, station_id, pump, _type, opened = parts
    if scope != "REAL":
        raise AssessError(
            "NOT_AVAILABLE", "evidence for scenario and family alerts needs inject.apply, not built yet"
        )
    a = assess_station(station_id, as_of)
    finding = next((f for f in a.queue if f.alert_id == alert_id), None)
    if finding is None:
        raise AssessError(
            "UNKNOWN_ALERT",
            f"alert {alert_id!r} is not open at {as_of:%Y-%m-%dT%H:%M:%SZ}",
            [f.alert_id for f in a.queue],
        )
    b = _bundle(station_id, as_of)
    d = b.daily
    rows = d[(d["pump_id"] == pump) & (d["day"] >= d["day"].max() - pd.Timedelta(days=89))] if len(d) else d
    trace = [
        TraceRow(
            day=r.day.date(), quality=r.quality, valid_cycles=int(r.valid_cycles), excluded={}, ci=_f(r.ci),
            base_median=_f(np.exp(r.base_median)), base_mad=_f(r.base_mad), z=_f(r.z), common=_f(r.common),
            u=_f(r.u), cusum=float(r.cusum), status=r.status, rain_mm=_f(r.rain_mm),
            run_median_s=_f(r.run_median_s), expected_run_s=None,
        )
        for r in rows.itertuples()
    ]  # fmt: skip
    prev = rows["status"].shift(fill_value="INSUFFICIENT_EVIDENCE")
    transitions = [
        Transition(on=r.day.date(), from_status=p, to_status=r.status, reason=r.transition_reason)
        for r, p in zip(rows.itertuples(), prev)
        if isinstance(r.transition_reason, str)
    ]
    day = pd.Timestamp(finding.opened_on)
    ev = b.sd.events[(b.sd.events["ts"] >= day) & (b.sd.events["ts"] < day + pd.Timedelta(days=1))]
    ev = ev[ev["pump_id"] == pump] if pump != "STATION" else ev
    lv = b.sd.level[(b.sd.level["ts"] >= day) & (b.sd.level["ts"] < day + pd.Timedelta(days=1))]
    today = rows.iloc[-1] if len(rows) else None
    flags = sorted({f for fl in ([] if today is None else [today.level_flags]) for f in fl})
    supporting = [finding.summary] + [t.reason for t in transitions[-1:]]
    return Evidence(
        alert_id=alert_id, station_id=station_id, pump_id=finding.pump_id, origin="REAL_REPLAY", as_of_utc=as_of,
        finding=finding, rain=a.rain, quality_flags=flags, supporting=supporting,
        contradictory=[f"{p.pump_id}: evidence {p.quality}" for p in a.pumps if p.pump_id == pump and p.quality != "SUFFICIENT"],
        unavailable=["expected run time at today's inflow", "excluded cycle counts per day", "motor current, alarms and setpoints (not in this dataset)"],
        trace=trace, transitions=transitions,
        raw_events=[RawEvent(ts=r.ts.tz_localize("UTC"), pump_id=r.pump_id, state="ON" if r.state == 1 else "OFF", signal_id=r.signal_id) for r in ev.head(500).itertuples()],
        level=[LevelPoint(ts=r.ts.tz_localize("UTC"), value=r.value, units=r.units) for r in lv.head(1440).itertuples()],
        level_signal_id=lv["signal_id"].iloc[0] if len(lv) else None,
        thresholds=Thresholds(h_w=b.p.h_w, h_i=b.p.h_i, min_effect=b.p.min_effect),
        work_order=explain.work_order(finding, station_id), provenance=a.provenance,
    )  # fmt: skip


def timeline(station_id: str, scenario_id: str | None, start: datetime, end: datetime) -> list[TimelineDay]:
    start, end = parse_time(start), parse_time(end)
    check(station_id, scenario_id, end)
    check(station_id, scenario_id, start)
    if end < start or (end - start).days > 400:
        raise AssessError("BAD_TIMESTAMP", "end must be on or after start and at most 400 days after it")
    # Only days complete before `end` (the as_of of the last frame): no data after `end` is read.
    d = _bundle(station_id, end).daily
    d = d[
        (d["day"] >= features.to_naive_utc(start).floor("D"))
        & (d["day"] < features.to_naive_utc(end).floor("D"))
    ]
    return [
        TimelineDay(
            day=day.date(), station_status=_status_quality(rows, set())[0],
            pumps=[
                TimelinePump(pump_id=r.pump_id, status=r.status, ci=_f(r.ci), base_median=_f(np.exp(r.base_median)), cusum=float(r.cusum))
                for r in rows.itertuples()
            ],
        )
        for day, rows in d.groupby("day")
    ]  # fmt: skip


def replay_case(case_id: str) -> ReplayResult:
    if not re.match(ID_PATTERN, case_id) or (not case_id.startswith("F") and case_id not in scenario_ids()):
        raise AssessError("UNKNOWN_CASE", f"unknown case {case_id!r}", scenario_ids())
    raise AssessError("NOT_AVAILABLE", "replays need inject.apply (fault injection), which is not built yet")
