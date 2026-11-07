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
  priority: number; opened_on: string; days_open: number;
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
export interface ToolError { code: string; message: string; allowed: string[] }
