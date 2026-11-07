// Mirrors backend/app/contracts.py as locked in ARCHITECTURE.md section 7.
// Replace with the generated/real contracts once Dhruv's contracts.py lands; keep names identical.
export type Status = "NORMAL" | "WATCH" | "INVESTIGATE" | "INSUFFICIENT_EVIDENCE" | "SOURCE_OFFLINE";
export type Quality = "SUFFICIENT" | "PARTIAL" | "INSUFFICIENT" | "SOURCE_OFFLINE";
export type Origin = "REAL_REPLAY" | "SYNTHETIC_INJECTION" | "SIMULATED_INCIDENT";
export type FindingType =
  | "CAPACITY_DROP" | "STATION_WIDE_CHANGE" | "PUMP_NOT_RUNNING"
  | "SOURCE_SILENT" | "HIGH_LEVEL" | "SENSOR_FAULT";

export interface Provenance {
  source_hash: string; scenario_hash: string | null; model_version: string;
  code_version: string; signal_ids: string[];
}
export interface PumpState {
  pump_id: string; status: Status; quality: Quality;
  ci_today: number | null; ci_baseline: number | null; capacity_change_pct: number | null;
  cusum: number; valid_cycles: number; runs: number;
  run_median_s: number | null; expected_run_s: number | null;
}
export interface Finding {
  alert_id: string; type: FindingType; pump_id: string | null; status: Status;
  priority: number; opened_on: string; since_utc: string; days_open: number;
  observed: number | null; expected: number | null; units: string; change_pct: number | null;
  summary: string; possible_causes: string[]; inspection: string[];
}
export interface RainContext { today_mm: number | null; last_72h_mm: number | null; source: string }
export interface StormOutlook {
  issued_on: string; forecast_rain_48h_in: number; max_gust_48h_mph: number; storm_ahead: boolean;
}
export interface StationAssessment {
  station_id: string; display_name: string; as_of_utc: string; origin: Origin;
  scenario_id: string | null; status: Status; quality: Quality;
  pumps: PumpState[]; queue: Finding[]; safety: Finding[]; rain: RainContext;
  storm: StormOutlook | null; missing_evidence: string[];
  explanation: string; recommended_action: string; provenance: Provenance;
}
export interface TraceRow {
  day: string; quality: Quality; valid_cycles: number; ci: number | null; base_median: number | null;
  base_mad: number | null; z: number | null; common: number | null; u: number | null; cusum: number; status: Status;
}
export interface Transition { on: string; from_status: Status; to_status: Status; reason: string }
export interface RawEvent { ts: string; pump_id: string; state: "ON" | "OFF"; signal_id: string }
export interface LevelPoint { ts: string; value: number; units: string }
export interface WorkOrder {
  title: string; station_id: string; pump_id: string | null; priority: string; requested_by: string;
  checks: string[]; evidence_alert_id: string; caveats: string[];
}
export interface Evidence {
  alert_id: string; station_id: string; pump_id: string | null; origin: Origin; as_of_utc: string;
  finding: Finding; rain: RainContext; quality_flags: string[];
  supporting: string[]; contradictory: string[]; unavailable: string[];
  trace: TraceRow[]; transitions: Transition[]; raw_events: RawEvent[]; level: LevelPoint[];
  work_order: WorkOrder; provenance: Provenance;
}
export interface AskResult {
  answer_markdown: string | null; withheld: boolean; tool_calls: { tool: string; args: unknown; ok: boolean }[];
  grounding: { passed: boolean; unmatched_numbers: string[]; forbidden_phrases: string[] };
  model: string; fallback_dropped: boolean;
}
// PROPOSED shape for GET /api/scenarios (not in section 7 yet; asked on the board). Mirrors the scenario TOML fields.
export interface ScenarioFact {
  label: string; value: string; status: "VERIFIED" | "UNVERIFIED"; confidence: number; source: string | null; source_url: string | null;
}
export type Detectability = "PREDICTABLE_DAYS_AHEAD" | "DETECTABLE_AT_ONSET";
export interface ScenarioVariant {
  variant: "A" | "B"; scenario_id: string; name: string; confidence: number; reason: string;
  detectability: Detectability; failure_at: string;
}
export interface ScenarioCard {
  id: string; title: string; version: string; scenario_hash: string;
  facts: ScenarioFact[]; outcome_facts: ScenarioFact[]; variants: ScenarioVariant[];
}
export interface ScenariosResponse { scenarios: ScenarioCard[]; dev_cases: { case_id: string; family: string; title: string }[] }
export interface Sensitivity { label: string; simulated_gal: number }
export interface Outcome { no_warning_gal: number; with_dragonfly_gal: number; sensitivity: Sensitivity[]; assumptions: string[] }
export interface BenchmarkRun { first_investigate_at: string | null; lead_time_h: number | null; incident_opens: number }
export interface ReplayResult {
  case_id: string; origin: Origin; family: string; title: string; truth: Record<string, unknown>;
  timeline: TimelineDay[]; first_watch_at: string | null; first_investigate_at: string | null;
  failure_at: string | null; lead_time_h: number | null; outcome: Outcome | null; benchmarks: Record<string, BenchmarkRun>;
}
export interface StationInfo {
  station_id: string; display_name: string; pumps: string[]; origin: Origin;
  scenario_id: string | null; as_of_min: string; as_of_max: string;
  outage_windows: [string, string][];
}
export interface StationsResponse { stations: StationInfo[]; source_hash: string; model_version: string }
export interface TimelinePump { pump_id: string; status: Status; ci: number | null; base_median: number | null; cusum: number }
export interface TimelineDay { day: string; station_status: Status; pumps: TimelinePump[] }
export interface ToolError { code: string; message: string; allowed: string[] }
