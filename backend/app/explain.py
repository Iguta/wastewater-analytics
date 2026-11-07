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
    ],
    "STATION_WIDE_CHANGE": [
        "Confirm level setpoints unchanged",
        "Force-main restriction or air",
        "Common discharge valves",
    ],
    "PUMP_NOT_RUNNING": ["Pump fail or overload alarm", "HOA switch position"],
    "SOURCE_SILENT": [
        "Station power and RTU communications",
        "Dispatch if level is unknown in wet weather",
    ],
    "SENSOR_FAULT": ["Level transducer", "Rely on floats and SCADA alarms until fixed"],
    "HIGH_LEVEL": ["Level against the SCADA high-level alarm (SCADA-equivalent; real setpoints unknown)"],
}
# The section 10.7 template ends "not a confirmed diagnosis", but section 10.7 also bans "confirmed".
CAVEAT = "This is a draft from a detector, not a diagnosis."


def _num(x, nd=1):
    return "unknown" if x is None else f"{x:.{nd}f}"


def explanation(
    station: str, status: str, finding: Finding | None, pump: PumpState | None, missing: list[str]
) -> str:
    """Section 10.7 template. Without a finding, state only the status and what is missing."""
    gaps = f"Missing evidence: {'; '.join(missing)}" if missing else "No evidence is missing"
    if finding is None:
        return f"Station {station}: {status}. {gaps}. {CAVEAT}"
    if pump is None:
        return f"Station {station}: {status}. {finding.summary}. {gaps}. Check: {'; '.join(CHECKLISTS[finding.type])}. {CAVEAT}"
    change = "unknown" if pump.capacity_change_pct is None else f"{abs(pump.capacity_change_pct):.0f}"
    return (
        f"Station {station} {pump.pump_id}: {status}. Pumping capacity is {change}% below this pump's normal "
        f"for {finding.days_open} days ({_num(pump.ci_today)} vs {_num(pump.ci_baseline)} per hour; "
        f"run time {_num(pump.run_median_s, 0)} s vs {_num(pump.expected_run_s, 0)} s expected at today's "
        f"inflow). Rain is not used to excuse this finding. {gaps}. "
        f"Check: {'; '.join(CHECKLISTS[finding.type])}. {CAVEAT}"
    )


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
