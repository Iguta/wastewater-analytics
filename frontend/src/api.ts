import type { AskResult, EvaluationReport, Evidence, ReplayResult, ScenariosResponse, StationAssessment, StationsResponse, TimelineDay, ToolError } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public toolError?: ToolError) {
    super(message);
  }
}

// Every non-2xx body is a ToolError (section 8.2). A raw 422 never reaches the screen.
async function get<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "Can't reach the Dragonfly server");
  }
  if (!res.ok) {
    let toolError: ToolError | undefined;
    try { toolError = await res.json(); } catch { /* not JSON */ }
    throw new ApiError(res.status, toolError?.message ?? `HTTP ${res.status}`, toolError);
  }
  return res.json() as Promise<T>;
}

// Section 10.1 copy for a dead or failing server; a 4xx with a ToolError body says what the server said.
export function errorText(e: unknown): string {
  if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.toolError?.message) return `${e.toolError.message} (HTTP ${e.status}).`;
  return `Can't reach the Dragonfly server (HTTP ${e instanceof ApiError && e.status ? e.status : "no response"}).`;
}

export const api = {
  health: () => get<{ status: string; model_version: string; source_hash: string; code_version: string }>("/api/health"),
  assess: (stationId: string, asOfUtc: string, scenarioId?: string, signal?: AbortSignal) =>
    get<StationAssessment>(
      `/api/assess?station_id=${encodeURIComponent(stationId)}&as_of_utc=${encodeURIComponent(asOfUtc)}` +
        (scenarioId ? `&scenario_id=${encodeURIComponent(scenarioId)}` : ""),
      { signal },
    ),
  stations: (scenarioId?: string | null) =>
    get<StationsResponse>("/api/stations" + (scenarioId ? `?scenario_id=${encodeURIComponent(scenarioId)}` : "")),
  timeline: (stationId: string, scenarioId: string | null, start: string, end: string, signal?: AbortSignal) =>
    get<TimelineDay[]>(
      `/api/timeline?station_id=${encodeURIComponent(stationId)}&start=${start}&end=${end}` +
        (scenarioId ? `&scenario_id=${encodeURIComponent(scenarioId)}` : ""),
      { signal },
    ),
  evidence: (alertId: string, asOfUtc: string) =>
    get<Evidence>(`/api/evidence?alert_id=${encodeURIComponent(alertId)}&as_of_utc=${encodeURIComponent(asOfUtc)}`),
  ask: (body: { question: string; station_id?: string; as_of_utc?: string; scenario_id?: string }, signal: AbortSignal) =>
    get<AskResult>("/api/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), signal }),
  scenarios: () => get<ScenariosResponse>("/api/scenarios"),
  replay: (caseId: string) => get<ReplayResult>(`/api/replay?case_id=${encodeURIComponent(caseId)}`),
  evaluation: () => get<EvaluationReport>("/api/evaluation"),
};
