"""Deterministic operator copy (ARCHITECTURE.md section 10.7). No model call, no probabilities."""

from __future__ import annotations

from .contracts import Finding, PumpState, WorkOrder

CHECKLISTS = {
    "CAPACITY_DROP": [
        "Impeller clog or ragging",
        "Discharge valve fully open and check valve free",
        "Air binding",
        "Drawdown test for actual pump rate",
        "Motor current vs nameplate if available",
        "Bring: drawdown test kit, clamp ammeter, impeller-access tools, rag hook",
    ],
    "STATION_WIDE_CHANGE": [
        "Confirm level setpoints unchanged",
        "Force-main restriction or air",
        "Common discharge valves",
        "Bring: pressure gauge, valve key, clamp ammeter",
    ],
    "PUMP_NOT_RUNNING": [
        "Pump fail or overload alarm",
        "HOA switch position",
        "Bring: clamp ammeter, multimeter, lockout tags",
    ],
    "SOURCE_SILENT": [
        "Station power and RTU communications",
        "Dispatch if level is unknown in wet weather",
        "Bring: portable generator, RTU battery",
    ],
    "SENSOR_FAULT": [
        "Level transducer",
        "Rely on floats and SCADA alarms until fixed",
        "Bring: spare level transducer",
    ],
    "HIGH_LEVEL": [
        "Level against the SCADA high-level alarm (SCADA-equivalent; real setpoints unknown)",
        "Bring: sounding tape, portable pump",
    ],
}
# The section 10.7 template ends "not a confirmed diagnosis", but section 10.7 also bans "confirmed".
CAVEAT = "This is a draft from a detector, not a diagnosis."


def _expected(seconds):
    # shortcut: expected run time is not computed yet (needs per-cycle data); say so rather than print "unknown s".
    return (
        "expected run time not yet computed"
        if seconds is None
        else f"vs {seconds:.0f} s expected at today's inflow"
    )


def _num(x, nd=1):
    return "unknown" if x is None else f"{x:.{nd}f}"


def explanation(
    station: str, status: str, finding: Finding | None, pump: PumpState | None, missing: list[str]
) -> str:
    """Section 10.7 template. Without a finding, state only the status and what is missing."""
    gaps = f"Missing evidence: {'; '.join(missing)}" if missing else "No evidence is missing"
    if finding is None:
        return f"Wessex {station}: {status}. {gaps}. {CAVEAT}"
    if pump is None:
        return f"Wessex {station}: {status}. {finding.summary}. {gaps}. Check: {'; '.join(CHECKLISTS[finding.type])}. {CAVEAT}"
    change = "unknown" if pump.capacity_change_pct is None else f"{abs(pump.capacity_change_pct):.0f}"
    return (
        f"Wessex {station} {pump.pump_id}: {status}. Pumping capacity is {change}% below this pump's normal "
        f"for {finding.days_open} days ({_num(pump.ci_today)} vs {_num(pump.ci_baseline)} per hour; "
        f"run time {_num(pump.run_median_s, 0)} s, {_expected(pump.expected_run_s)}). "
        f"Rain is not used to excuse this finding. {gaps}. "
        f"Check: {'; '.join(CHECKLISTS[finding.type])}. {CAVEAT}"
    )


def priority_reason(f: Finding, rank: int, total: int, quality: str | None) -> str:
    """One line from fields the finding already has; says why it sits at this rank."""
    if f.change_pct is None:
        what = f.type.lower().replace("_", " ")
    else:
        what = f"{'largest ' if rank == 1 else ''}capacity loss (\u2212{abs(f.change_pct):.0f}%)"
    parts = [what, f"{f.days_open} day{'s' * (f.days_open != 1)} open"]
    if quality:
        parts.append(f"evidence {quality.replace('_', ' ').capitalize()}")
    return f"Rank {rank} of {total}: {', '.join(parts)}"


def work_order(finding: Finding, station_id: str) -> WorkOrder:
    return WorkOrder(
        title=f"Inspect {station_id} {finding.pump_id or 'station'}: {finding.type}",
        station_id=station_id,
        pump_id=finding.pump_id,
        priority=finding.status,
        checks=CHECKLISTS[finding.type],
        evidence_alert_id=finding.alert_id,
        caveats=[CAVEAT, "Verify on site before acting."],
    )
