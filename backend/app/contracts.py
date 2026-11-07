"""Wire contracts for REST, MCP and the agent (ARCHITECTURE.md section 7)."""

from __future__ import annotations

from datetime import date, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field

Status = Literal["NORMAL", "WATCH", "INVESTIGATE", "INSUFFICIENT_EVIDENCE", "SOURCE_OFFLINE"]
Quality = Literal["SUFFICIENT", "PARTIAL", "INSUFFICIENT", "SOURCE_OFFLINE"]
Origin = Literal["REAL_REPLAY", "SYNTHETIC_INJECTION", "SIMULATED_INCIDENT"]
FindingType = Literal[
    "CAPACITY_DROP", "STATION_WIDE_CHANGE", "PUMP_NOT_RUNNING", "SOURCE_SILENT", "HIGH_LEVEL", "SENSOR_FAULT"
]
ErrorCode = Literal[
    "UNKNOWN_STATION",
    "UNKNOWN_SCENARIO",
    "UNKNOWN_ALERT",
    "UNKNOWN_CASE",
    "BAD_TIMESTAMP",
    "AS_OF_OUT_OF_RANGE",
    "AGENT_ERROR",
    "AGENT_TIMEOUT",
    "NO_REPORT",
    "BAD_QUESTION",
    "BAD_FEEDBACK",
    "NOT_AVAILABLE",  # the piece of the model that would answer is not built yet (not in section 7)
]

# One pattern for scenario_id and case_id (section 5.6).
ID_PATTERN = r"^([a-z0-9_]+:[AB]|F[1-7]-\d{1,4})$"
# alert_id: scope (REAL or scenario_id), station, pump or STATION, finding type, opened date.
ALERT_ID_PATTERN = r"^(REAL|[a-z0-9_]+:[AB]):\d+:[A-Za-z0-9]+:[A-Z_]+:\d{4}-\d{2}-\d{2}$"

# Any offset is accepted on input and normalised, so every serialised datetime ends in Z.
UtcDatetime = Annotated[AwareDatetime, AfterValidator(lambda d: d.astimezone(timezone.utc))]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(Contract):
    source_hash: str
    scenario_hash: str | None
    model_version: str
    code_version: str
    signal_ids: list[str]


class PumpState(Contract):
    pump_id: str
    status: Status
    quality: Quality
    ci_today: float | None
    ci_baseline: float | None
    capacity_change_pct: float | None
    cusum: float
    valid_cycles: int
    runs: int
    run_median_s: float | None
    expected_run_s: float | None


class Finding(Contract):
    alert_id: str
    type: FindingType
    pump_id: str | None
    status: Status
    priority: int  # 1 = highest
    opened_on: date
    since_utc: UtcDatetime  # first minute or day the condition held
    days_open: int
    observed: float | None
    expected: float | None
    units: str
    change_pct: float | None
    summary: str
    possible_causes: list[str]
    inspection: list[str]
    priority_reason: str | None = None


class RainContext(Contract):
    today_mm: float | None
    last_72h_mm: float | None
    source: str


class StormOutlook(Contract):
    issued_on: date
    forecast_rain_48h_in: float
    max_gust_48h_mph: float
    storm_ahead: bool


class StationAssessment(Contract):
    station_id: str
    display_name: str
    as_of_utc: UtcDatetime
    origin: Origin
    scenario_id: str | None
    status: Status
    quality: Quality
    pumps: list[PumpState]
    queue: list[Finding]
    safety: list[Finding]
    rain: RainContext
    storm: StormOutlook | None
    missing_evidence: list[str]
    explanation: str
    recommended_action: str
    provenance: Provenance


class TraceRow(Contract):
    day: date
    quality: Quality
    valid_cycles: int
    excluded: dict[str, int]  # cycles excluded, by section 3.5 flag
    ci: float | None
    base_median: float | None
    base_mad: float | None
    z: float | None
    common: float | None
    u: float | None
    cusum: float
    status: Status
    rain_mm: float | None
    run_median_s: float | None
    expected_run_s: float | None


class Transition(Contract):
    on: date
    from_status: Status
    to_status: Status
    reason: str


class RawEvent(Contract):
    ts: UtcDatetime
    pump_id: str
    state: Literal["ON", "OFF"]
    signal_id: str


class LevelPoint(Contract):
    ts: UtcDatetime
    value: float
    units: str


class Thresholds(Contract):
    h_w: float
    h_i: float
    min_effect: float


class WorkOrder(Contract):
    title: str
    station_id: str
    pump_id: str | None
    priority: str
    requested_by: str = "Dragonfly draft - needs human review"
    checks: list[str]
    evidence_alert_id: str
    caveats: list[str]


class Evidence(Contract):
    alert_id: str
    station_id: str
    pump_id: str | None
    origin: Origin
    as_of_utc: UtcDatetime
    finding: Finding
    rain: RainContext
    quality_flags: list[str]
    supporting: list[str]
    contradictory: list[str]
    unavailable: list[str]
    trace: list[TraceRow]  # <= 90
    transitions: list[Transition]
    raw_events: list[RawEvent]  # <= 500, trigger day
    level: list[LevelPoint]  # <= 1440, trigger day
    level_signal_id: str | None
    thresholds: Thresholds  # from params.toml, so the UI never hard-codes them
    work_order: WorkOrder
    provenance: Provenance


class TimelinePump(Contract):
    pump_id: str
    status: Status
    ci: float | None
    base_median: float | None
    cusum: float


class TimelineDay(Contract):
    day: date
    station_status: Status
    pumps: list[TimelinePump]


class Sensitivity(Contract):
    label: str
    simulated_gal: float


class Outcome(Contract):
    no_warning_gal: float
    with_dragonfly_gal: float
    sensitivity: list[Sensitivity]
    assumptions: list[str]


class BenchmarkRun(Contract):
    first_investigate_at: UtcDatetime | None
    lead_time_h: float | None
    incident_opens: int


class ReplayResult(Contract):
    case_id: str
    origin: Origin
    family: str
    title: str
    truth: dict
    timeline: list[TimelineDay]
    first_watch_at: UtcDatetime | None
    first_investigate_at: UtcDatetime | None
    failure_at: UtcDatetime | None
    lead_time_h: float | None
    outcome: Outcome | None
    benchmarks: dict[str, BenchmarkRun]
    source_offline_after_min: float | None
    sensor_fault_flagged: bool


class StationInfo(Contract):
    station_id: str
    display_name: str
    pumps: list[str]
    origin: Origin
    scenario_id: str | None
    as_of_min: UtcDatetime
    as_of_max: UtcDatetime
    outage_windows: list[tuple[UtcDatetime, UtcDatetime]]  # real data gaps to mark on the scrubber


class StationsResponse(Contract):
    stations: list[StationInfo]
    source_hash: str
    model_version: str


class Fact(Contract):
    label: str
    value: str
    status: Literal["VERIFIED", "UNVERIFIED"]
    confidence: int  # 0-100
    source: str
    source_url: str | None


class VariantCard(Contract):
    variant: Literal["A", "B"]
    scenario_id: str
    name: str
    confidence: int
    reason: str
    detectability: Literal["PREDICTABLE_DAYS_AHEAD", "DETECTABLE_AT_ONSET", "NOT_DETECTABLE"]
    failure_at: UtcDatetime


class ScenarioCard(Contract):
    id: str
    title: str
    version: str
    scenario_hash: str
    facts: list[Fact]
    outcome_facts: list[Fact]
    variants: list[VariantCard]


class DevCase(Contract):
    case_id: str
    experiment: Literal["storm_test", "break_sensor", "cut_power", "one_bad_day"] | None


class ScenariosResponse(Contract):
    scenarios: list[ScenarioCard]
    dev_cases: list[DevCase]  # the Lab's fixed dev cases (section 5.6)


class Count(Contract):
    k: int
    n: int


class BenchmarkRow(Contract):
    caught: Count
    median_lead_days: float | None
    false_storm: Count
    false_duty: Count
    false_transient: Count
    real_alerts_per_pump_6mo: float


class HeatCell(Contract):
    loss: float
    ramp: float
    k: int
    n: int


class ProxyRow(Contract):
    tier: Literal["dev", "test"]
    group: Literal["demo_3", "untouched_21"]
    episodes: int
    preceded: int


class EvaluationReport(Contract):
    model_version: str
    code_version: str
    benchmarks: dict[Literal["A", "B", "C", "C-persistence", "C-inhibition", "C-quality"], BenchmarkRow]
    heatmap: list[HeatCell]
    proxy: list[ProxyRow]
    test_scored: int
    gates: dict[str, bool]


class ToolCall(Contract):
    tool: str
    args: dict
    ok: bool


class Grounding(Contract):
    passed: bool
    unmatched_numbers: list[str]
    forbidden_phrases: list[str]


class AskResult(Contract):
    answer_markdown: str | None
    withheld: bool
    tool_calls: list[ToolCall]
    grounding: Grounding
    model: str
    fallback_dropped: bool


class Feedback(Contract):
    """One operator verdict on an alert. Logged only; never changes an assessment."""

    alert_id: str = Field(pattern=ALERT_ID_PATTERN)
    verdict: Literal["found_issue", "checked_ok", "not_sure"]
    by: str = Field(min_length=1, max_length=80)
    note: str = Field(max_length=500)
    at_utc: UtcDatetime


class ToolError(Contract):
    code: ErrorCode
    message: str
    allowed: list[str]
