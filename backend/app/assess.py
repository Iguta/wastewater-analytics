"""The David <-> Dhruv seam (ARCHITECTURE.md 8.1): detector output mapped to the section 7 models.

Real stations load from data.load; scenario and family ids load scenarios.case_stream(id)[0] (truth is never passed on).
Inputs are cut at as_of BEFORE features are computed; results are cached on the full instant.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, detect, evaluate, explain, features, outcome, params, scenarios
from .contracts import (
    ID_PATTERN,
    BenchmarkRun,
    Evidence,
    Finding,
    LevelPoint,
    Outcome,
    Provenance,
    PumpState,
    RainContext,
    RawEvent,
    ReplayResult,
    Sensitivity,
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


def known_case(case_id: str) -> bool:
    if not re.match(ID_PATTERN, case_id):
        return False
    if ":" in case_id:
        return case_id in scenario_ids()
    fam, seed = case_id.split("-")
    return int(seed) % 1000 < evaluate.FAMILIES[fam] and int(seed) // 1000 < 2


@lru_cache(maxsize=4)
def _case(case_id: str):
    return scenarios.case_stream(case_id)


def check(station_id: str, scenario_id: str | None, as_of: datetime) -> None:
    if station_id not in data.STATIONS:
        raise AssessError("UNKNOWN_STATION", f"unknown station {station_id!r}", list(data.STATIONS))
    if scenario_id is not None:
        if not known_case(scenario_id):
            raise AssessError("UNKNOWN_SCENARIO", f"unknown scenario {scenario_id!r}", scenario_ids())
        case_station = _case(scenario_id)[0].station_id
        if station_id != case_station:
            raise AssessError(
                "UNKNOWN_STATION", f"{scenario_id} runs on station {case_station}", [case_station]
            )
    elif not REAL_MIN <= as_of <= REAL_MAX:
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
    meta: dict
    scope: str  # "REAL" or the case id; prefixes alert ids


@lru_cache(maxsize=32)
def _bundle(station_id: str, as_of: datetime, scenario_id: str | None = None) -> _Bundle:
    if scenario_id:
        full, _truth, meta = _case(scenario_id)  # truth is dropped here: detection never sees it
        sd = replace(full)
    else:
        sd, meta = data.load(station_id), {"origin": "REAL_REPLAY"}
    end = features.to_naive_utc(as_of)
    sd.events = sd.events[sd.events["ts"] < end]
    sd.level = sd.level[sd.level["ts"] < end]
    sd.rain = sd.rain[sd.rain["ts_hour"] < end]
    p = params.load()
    daily = features.daily_table(sd.events, sd.level, sd.rain, as_of, station_id, sd.quality_counts)
    scope = scenario_id or "REAL"
    return _Bundle(
        sd, detect.run(daily, p, scope), detect.realtime(sd.events, sd.level, as_of, p), p, meta, scope
    )


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
    scope = b.scope
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
                        f"{scope}:{station_id}:{r.pump_id}:PUMP_NOT_RUNNING:{opened}",
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
                    f"{scope}:{station_id}:STATION:STATION_WIDE_CHANGE:{opened}",
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
        sid = f"{scope}:{station_id}:STATION:{e['type']}:{since.date()}"
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
    quality = {r.pump_id: r.quality for r in d[d["day"] == d["day"].max()].itertuples()} if len(d) else {}
    for i, f in enumerate(out, 1):
        f.priority = i
        f.priority_reason = explain.priority_reason(f, i, len(out), quality.get(f.pump_id))
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
    b = _bundle(station_id, as_of, scenario_id)
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
        station_id=station_id, display_name=f"Wessex {station_id}", as_of_utc=as_of, origin=b.meta["origin"],
        scenario_id=scenario_id, status=status, quality=quality, pumps=pumps, queue=queue,
        safety=[f for f in queue if f.type in SAFETY], rain=_rain(b, as_of), storm=None, missing_evidence=missing,
        explanation=explain.explanation(station_id, status, top, pump, missing),
        recommended_action=f"{order.title}. First check: {order.checks[0]}." if order else "No action from the detector.",
        provenance=Provenance(
            source_hash=b.sd.source_hash, scenario_hash=b.meta.get("scenario_hash"), model_version=b.p.version,
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
    scenario_id = None if scope == "REAL" else scope
    a = assess_station(station_id, as_of, scenario_id)
    finding = next((f for f in a.queue if f.alert_id == alert_id), None)
    if finding is None:
        raise AssessError(
            "UNKNOWN_ALERT",
            f"alert {alert_id!r} is not open at {as_of:%Y-%m-%dT%H:%M:%SZ}",
            [f.alert_id for f in a.queue],
        )
    b = _bundle(station_id, as_of, scenario_id)
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
        alert_id=alert_id, station_id=station_id, pump_id=finding.pump_id, origin=a.origin, as_of_utc=as_of,
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
    d = _bundle(station_id, end, scenario_id).daily
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


def _utc(t) -> datetime | None:
    return None if t is None else pd.Timestamp(t).tz_localize("UTC").to_pydatetime()


def _first_day(days, hit) -> datetime | None:
    """§4.6 timing: the first qualifying day D counts as raised at 00:00Z on D + 1."""
    d = next((d.day for d in days if hit(d)), None)
    return None if d is None else datetime.combine(d + timedelta(days=1), time.min, tzinfo=timezone.utc)


def _minute_scan(st: data.StationData, t0, p: params.Params) -> tuple[int | None, int | None, bool]:
    """Realtime findings after t0 (naive UTC): first minute of SOURCE_OFFLINE, first of HIGH_LEVEL, any SENSOR_FAULT.
    shortcut: every minute for 2 h, then +3/6/12 h (sensor flags use 24 h windows); upgrade if a case needs finer."""
    offline = high = None
    fault = False
    for m in [*range(1, 121), 180, 360, 720]:
        for e in detect.realtime(st.events, st.level, _utc(t0 + pd.Timedelta(minutes=m)), p):
            offline = m if offline is None and e["type"] == "SOURCE_SILENT" else offline
            high = m if high is None and e["type"] == "HIGH_LEVEL" and e["status"] == "INVESTIGATE" else high
            fault = fault or e["type"] == "SENSOR_FAULT"
    return offline, high, fault


def _outcome(case_id: str, meta: dict, first_inv, failure, notify_min) -> Outcome:
    """§5.5 counterfactual on the case's own scenario file; only the time until someone is told changes."""
    sid, var = case_id.split(":")
    s, _ = scenarios.load(sid)
    spec, no_warning = s["variants"][var], meta["outcome"]["no_system_gal"]
    rows = []
    if scenarios.v(spec["precursor_type"]) != "none":
        for r in (24, 48, 96):
            fixed = first_inv is not None and first_inv + timedelta(hours=r) < _utc(failure)
            rows.append(Sensitivity(label=f"repair {r} h", simulated_gal=0.0 if fixed else no_warning))
        note = "repair finishes R h after the first INVESTIGATE; a WATCH alone dispatches nobody; every other step as in the scenario"
    else:
        out_min = float(scenarios.v(s["outcome"]["outage_duration_min"]))
        storage = float(scenarios.v(s["station_standin"]["wet_well_usable_storage_gal"]))
        cap = float(scenarios.v(s["station_standin"]["pump_capacity_gpm_each"]))
        alarm_worked = not scenarios.v(spec["backup_failed"])
        if not alarm_worked and notify_min is not None:
            inflow = scenarios.scaled_inflow_gpm(s, scenarios.Analog(**meta["analog"]), data.load(None, sid))[
                0
            ]
        for d in (60, 180, 360):
            gal = no_warning
            if not alarm_worked and notify_min is not None:
                restore = failure + pd.Timedelta(minutes=notify_min + out_min - d)
                on = np.where((inflow.index >= failure) & (inflow.index < restore), 0.0, cap)
                caps = pd.DataFrame({"duty": on, "standby": on}, index=inflow.index)
                gal = outcome.simulate(inflow, caps, {"storage_gal": storage}).overflow_gal
            rows.append(Sensitivity(label=f"if staff would otherwise find out at {d} min", simulated_gal=gal))
        note = (
            "station alarm assumed to have worked: Dragonfly gains nothing"
            if alarm_worked
            else "notified at the first minute SOURCE_OFFLINE or HIGH_LEVEL holds; pumping restored at notification + (outage - discovery delay). The no-warning case is the scenario's own discovery delay; the total outage is fixed, so a longer assumed discovery leaves less repair time after Dragonfly's notice"
        )
    return Outcome(no_warning_gal=no_warning, with_dragonfly_gal=rows[1].simulated_gal, sensitivity=rows,
                   assumptions=[*meta["assumptions"], note, "with_dragonfly_gal is the middle sensitivity row; none is preferred"])  # fmt: skip


@lru_cache(maxsize=8)
def replay_case(case_id: str) -> ReplayResult:
    if not known_case(case_id):
        raise AssessError("UNKNOWN_CASE", f"unknown case {case_id!r}", scenario_ids())
    st, truth, meta = _case(case_id)
    p = params.load()
    end = _utc(max(st.events["ts"].max(), st.level["ts"].max()).floor("D"))
    tl = timeline(
        st.station_id, case_id, _utc(min(st.events["ts"].min(), st.level["ts"].min()).ceil("D")), end
    )
    daily = _bundle(st.station_id, end, case_id).daily
    watch = _first_day(tl, lambda d: d.station_status in ("WATCH", "INVESTIGATE"))
    inv = _first_day(tl, lambda d: d.station_status == "INVESTIGATE")
    onset = (
        ":" in case_id
        and scenarios.v(scenarios.load(case_id.split(":")[0])[0]["variants"][case_id[-1]]["precursor_type"])
        == "none"
    )
    spec = meta["case"].spec if "case" in meta else {}
    t0 = meta.get("failure_at", spec.get("failure", spec.get("start")))
    failure = _utc(t0)
    offline, high, fault = _minute_scan(st, t0, p) if t0 is not None else (None, None, False)
    lead = (
        None
        if onset or inv is None or failure is None or inv > failure
        else (failure - inv).total_seconds() / 3600
    )
    out = None
    if ":" in case_id:
        out = _outcome(
            case_id, meta, inv, t0, min((m for m in (offline, high) if m is not None), default=None)
        )
        if (
            watch is not None
            and watch <= failure
            and (onset or inv is None or watch < inv - pd.Timedelta(days=30))
        ):
            out.assumptions.append(
                f"stand-in history: the {st.station_id} stand-in carries real findings before the simulated failure "
                f"(first WATCH {watch:%Y-%m-%d}), unrelated to this scenario; lead time is not computed"
            )
    bench = {}
    for k, r in {"A": evaluate.bench_a(daily, p), "B": evaluate.bench_b(daily, p), "C": daily}.items():
        hit = r[r["status"] == "INVESTIGATE"]
        first = None if hit.empty else _utc(hit["day"].min() + pd.Timedelta(days=1))
        lag = (
            None
            if onset or first is None or failure is None or first > failure
            else (failure - first).total_seconds() / 3600
        )
        bench[k] = BenchmarkRun(
            first_investigate_at=first, lead_time_h=lag, incident_opens=int(hit["incident_id"].nunique())
        )
    return ReplayResult(
        case_id=case_id, origin=meta["origin"], family=case_id.split(":")[0] if ":" in case_id else case_id.split("-")[0],
        title=f"{case_id} on station {st.station_id}", truth={"transforms": truth}, timeline=tl, first_watch_at=watch,
        first_investigate_at=inv, failure_at=failure, lead_time_h=lead, outcome=out, benchmarks=bench,
        source_offline_after_min=offline, sensor_fault_flagged=fault,
    )  # fmt: skip
