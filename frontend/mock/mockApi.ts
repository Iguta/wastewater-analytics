// DEV ONLY. Enabled with `MOCK=1 npm run dev`; never bundled into `npm run build`.
// Hand-made payloads shaped like ARCHITECTURE section 7, to build the UI before the backend exists.
// Numbers here are placeholders, not model output. Replace with fixtures/ui/ samples when they land.
import type { Plugin } from "vite";

const STATIONS = [
  { station_id: "44371", display_name: "Wessex 44371", pumps: ["P1", "P2"] },
  { station_id: "45385", display_name: "Wessex 45385", pumps: ["P1", "P2"] },
  { station_id: "45078", display_name: "Wessex 45078", pumps: ["P1", "P2", "P3"] },
];
const hash = "mock0000";
const prov = { source_hash: hash, scenario_hash: null, model_version: "dragonfly-ci-v1", code_version: "mock", signal_ids: [] };
const dayAdd = (d: string, n: number) => new Date(Date.parse(d + "T00:00:00Z") + n * 864e5).toISOString().slice(0, 10);

const MORN = "bloomington_morningside_2024_04_11";
const FACT = (label: string, value: string, status: "VERIFIED" | "UNVERIFIED", confidence: number, source: string | null) => ({ label, value, status, confidence, source, source_url: null });
const SCENARIOS = [
  { id: MORN, title: "Bloomington, Morningside Lift Station equipment-failure overflow, 2024-04-11", version: "v4", scenario_hash: "mockhash1",
    facts: [FACT("Date", "2024-04-11", "VERIFIED", 100, "kfaf-msfz"), FACT("Station", "Morningside Lift Station", "VERIFIED", 100, "kfaf-msfz"), FACT("Cause in record", "Equipment failure", "VERIFIED", 100, "kfaf-msfz"), FACT("Rain in record", "1.18 in", "VERIFIED", 100, "kfaf-msfz")],
    outcome_facts: [FACT("Reported overflow", "14,310 gal (record)", "VERIFIED", 100, "kfaf-msfz"), FACT("Affected", "Lake Monroe-Stephens Creek drainage basin", "VERIFIED", 80, "kfaf-msfz")],
    variants: [
      { variant: "A", scenario_id: `${MORN}:A`, name: "Progressive impeller ragging or clog", confidence: 40, reason: "Upstream blockage 4 days earlier; timing fits a storm.", detectability: "PREDICTABLE_DAYS_AHEAD", failure_at: "2024-04-11T07:00:00Z" },
      { variant: "B", scenario_id: `${MORN}:B`, name: "Sudden pump, motor or control trip under storm load", confidence: 40, reason: "Starter contacts replaced in 2023; no precursor assumed.", detectability: "DETECTABLE_AT_ONSET", failure_at: "2024-04-11T07:00:00Z" },
    ] },
];
const scopeOf = (alertId: string) => { const s = alertId.split(":").slice(0, -4).join(":"); return s === "REAL" ? null : s; };
const sc = (id: string | null) => (id ? id.split(":")[0] : null);
const scenarioFailureDay = "2024-04-11";
function scenarioStatus(variant: string, pump: string, day: string): "NORMAL" | "WATCH" | "INVESTIGATE" {
  if (pump !== "P1") return "NORMAL";
  if (variant === "A") return day >= "2024-04-08" && day <= scenarioFailureDay ? "INVESTIGATE" : day >= "2024-04-06" && day < "2024-04-08" ? "WATCH" : "NORMAL";
  return "NORMAL";
}

function pumpStatus(station: string, pump: string, day: string): "NORMAL" | "WATCH" | "INVESTIGATE" {
  if (station === "44371" && pump === "P1") {
    if (day >= "2022-06-02" && day < "2022-06-11") return day >= "2022-06-03" ? "INVESTIGATE" : "WATCH";
  }
  if (station === "45078" && pump === "P3" && day >= "2022-06-01" && day <= "2022-06-05") return "WATCH";
  return "NORMAL";
}

function assess(station: string, day: string, scenario: string | null = null) {
  const s = STATIONS.find((x) => x.station_id === station)!;
  const pumps = s.pumps.map((p) => {
    const status = scenario ? scenarioStatus(scenario.split(":")[1], p, day) : pumpStatus(station, p, day);
    return { pump_id: p, status, quality: "SUFFICIENT", ci_today: status === "NORMAL" ? 30 : 16.3, ci_baseline: 30,
      capacity_change_pct: status === "NORMAL" ? 0.4 : -46, cusum: status === "NORMAL" ? 0.2 : 7.1,
      valid_cycles: 38, runs: 41, run_median_s: 140, expected_run_s: 95 };
  });
  const queue = pumps.filter((p) => p.status !== "NORMAL").map((p, i) => ({
    alert_id: `${scenario ?? "REAL"}:${station}:${p.pump_id}:CAPACITY_DROP:${scenario ? "2024-04-06" : "2022-06-01"}`, type: "CAPACITY_DROP", pump_id: p.pump_id, status: p.status,
    priority: i + 1, opened_on: scenario ? "2024-04-06" : "2022-06-01", since_utc: (scenario ? "2024-04-06" : "2022-06-01") + "T00:00:00Z", days_open: Math.max(1, Math.round((Date.parse(day) - Date.parse(scenario ? "2024-04-06" : "2022-06-01")) / 864e5) + 1),
    observed: p.ci_today, expected: p.ci_baseline, units: "/h", change_pct: p.capacity_change_pct,
    summary: p.status === "INVESTIGATE" ? "Investigate: inspect this pump" : "Watch: capacity is dropping",
    possible_causes: [], inspection: [],
  }));
  const worst = pumps.some((p) => p.status === "INVESTIGATE") ? "INVESTIGATE" : pumps.some((p) => p.status === "WATCH") ? "WATCH" : "NORMAL";
  return { station_id: station, display_name: s.display_name, as_of_utc: day + "T00:00:00Z", origin: scenario ? "SIMULATED_INCIDENT" : "REAL_REPLAY", scenario_id: scenario,
    status: worst, quality: "SUFFICIENT", pumps, queue, safety: [], rain: { today_mm: 0, last_72h_mm: 2.4, source: "mock" },
    storm: null, missing_evidence: [], explanation: "", recommended_action: "", provenance: prov };
}

export function mockApi(): Plugin {
  return {
    name: "dragonfly-mock-api",
    apply: "serve",
    configureServer(server) {
      if (!process.env.MOCK) return;
      server.middlewares.use("/api", (req, res) => {
        const u = new URL(req.url ?? "", "http://x");
        const q = u.searchParams;
        const send = (code: number, body: unknown) => { res.statusCode = code; res.setHeader("content-type", "application/json"); res.end(JSON.stringify(body)); };
        if (u.pathname === "/ask") return send(503, { code: "agent_offline", message: "agent offline", allowed: [] });
        if (u.pathname === "/health") return send(200, { status: "ok", model_version: "dragonfly-ci-v1", source_hash: hash, code_version: "mock" });
        if (u.pathname === "/evaluation") {
          const r = (k: number, n: number) => ({ k, n });
          const row = (caught: number, lead: number, fs: number, fd: number, ft: number, alerts: number) => ({ caught: r(caught, 100), median_lead_days: lead, false_storm: r(fs, 30), false_duty: r(fd, 30), false_transient: r(ft, 30), real_alerts_per_pump_6mo: alerts });
          const bins = { loss_bins: ["20-30%", "30-40%", "40-50%"], ramp_bins: ["7-14 d", "14-30 d"] };
          return send(200, { model_version: "dragonfly-ci-v1", code_version: "mock", test_scored: 1,
            benchmarks: { A: row(40, 1.0, 12, 9, 7, 3.1), B: row(70, 2.0, 6, 4, 5, 2.2), C: row(80, 3.0, 0, 0, 0, 0.5), "C-persistence": row(78, 3.0, 2, 1, 4, 1.1), "C-inhibition": row(80, 3.0, 0, 5, 0, 0.6), "C-quality": row(81, 3.0, 1, 0, 0, 0.9) },
            heatmap: { ...bins, cells: bins.loss_bins.flatMap((l, i) => bins.ramp_bins.map((m, j) => ({ loss: l, ramp: m, k: 15 + i * 3 + j * 2, n: i === 2 && j === 0 ? 12 : 25 }))) },
            proxy: [{ tier: "dev", episodes: 9, preceded: 5 }, { tier: "test", episodes: 3, preceded: 1 }],
            weak_labels: { episodes: 117, with_precursor: 16, warned: 7 }, caveats: [] });
        }
        if (u.pathname === "/scenarios") return send(200, { scenarios: SCENARIOS, dev_cases: [
          { case_id: "F2-0", family: "F2", title: "Storm test", experiment: "storm_test" }, { case_id: "F6-0", family: "F6", title: "Level sensor fault", experiment: "break_sensor" },
          { case_id: "F5-0", family: "F5", title: "Outage", experiment: "cut_power" }, { case_id: "F4-3", family: "F4", title: "Transient", experiment: "one_bad_day" } ] });
        if (u.pathname === "/replay") {
          const id = q.get("case_id")!; const A = id.endsWith(":A");
          if (/^F\d/.test(id)) return send(200, { case_id: id, origin: "SYNTHETIC_INJECTION", family: id.split("-")[0], title: id, truth: {}, timeline: Array.from({ length: 12 }, (_, i) => ({ day: dayAdd("2022-06-01", i), station_status: id.startsWith("F5") && i === 5 ? "SOURCE_OFFLINE" : id.startsWith("F4") && i === 5 ? "WATCH" : "NORMAL", pumps: [] })),
            first_watch_at: null, first_investigate_at: null, failure_at: null, lead_time_h: null, outcome: null,
            benchmarks: { A: { first_investigate_at: id.startsWith("F2") ? "2022-06-04T00:00:00Z" : null, lead_time_h: null, incident_opens: id.startsWith("F2") ? 2 : 0 }, B: { first_investigate_at: null, lead_time_h: null, incident_opens: 0 }, C: { first_investigate_at: null, lead_time_h: null, incident_opens: 0 } },
            source_offline_after_min: id.startsWith("F5") ? 10 : null, sensor_fault_flagged: id.startsWith("F6") });
          return send(200, { case_id: id, origin: "SIMULATED_INCIDENT", family: "incident", title: id, truth: { capacity_loss_24h: 0.6, ramp_days: 6, shape: "accelerating" }, timeline: [],
            first_watch_at: A ? "2024-04-07T00:00:00Z" : null, first_investigate_at: A ? "2024-04-09T00:00:00Z" : "2024-04-11T07:05:00Z", failure_at: "2024-04-11T07:00:00Z", lead_time_h: A ? 55 : 0,
            outcome: { no_warning_gal: 14310, with_dragonfly_gal: A ? 0 : 14310, sensitivity: A ? [{ label: "repair 24 h", simulated_gal: 0 }, { label: "repair 48 h", simulated_gal: 0 }, { label: "repair 96 h", simulated_gal: 14310 }] : [], assumptions: ["Mock numbers, not model output"] }, benchmarks: {} });
        }
        if (u.pathname === "/stations" && q.get("scenario_id")) return send(200, { source_hash: hash, model_version: "dragonfly-ci-v1", stations: [{ ...STATIONS[0], origin: "SIMULATED_INCIDENT", scenario_id: q.get("scenario_id"), as_of_min: "2024-03-12T07:00:00Z", as_of_max: "2024-04-14T07:00:00Z", outage_windows: [] }] });
        if (u.pathname === "/stations") return send(200, { source_hash: hash, model_version: "dragonfly-ci-v1",
          stations: STATIONS.map((s) => ({ ...s, origin: "REAL_REPLAY", scenario_id: null, as_of_min: "2022-03-16T00:00:00Z", as_of_max: "2024-01-01T00:00:00Z",
            outage_windows: [["2023-08-17T10:20:00Z", "2023-08-20T12:21:00Z"]] })) });
        if (u.pathname === "/assess") return send(200, assess(q.get("station_id")!, q.get("as_of_utc")!.slice(0, 10), q.get("scenario_id")));
        if (u.pathname === "/timeline") {
          const out = []; for (let d = q.get("start")!; d <= q.get("end")!; d = dayAdd(d, 1)) {
            const a = assess(q.get("station_id")!, d, q.get("scenario_id"));
            out.push({ day: d, station_status: a.status, pumps: a.pumps.map((p) => ({ pump_id: p.pump_id, status: p.status, ci: p.ci_today, base_median: p.ci_baseline, cusum: p.cusum })) });
          } return send(200, out);
        }
        if (u.pathname === "/evidence") {
          const [station, pump] = q.get("alert_id")!.split(":").slice(-4);
          const day = q.get("as_of_utc")!.slice(0, 10);
          const a = assess(station, day, scopeOf(q.get("alert_id")!));
          const finding = a.queue.find((f) => f.pump_id === pump) ?? a.queue[0];
          const trace = []; for (let i = 89; i >= 0; i--) {
            const d = dayAdd(day, -i); const s = pumpStatus(station, pump, d);
            const ci = s === "NORMAL" ? 30 + Math.sin(i) : 30 - Math.min(14, (89 - i - 80) * 2.5);
            trace.push({ day: d, quality: "SUFFICIENT", valid_cycles: 38, excluded: { LONG_RUN: 2 }, rain_mm: i % 7 === 0 ? 8 : 0.4, ci, base_median: 30, base_mad: 0.04, z: 0, common: 0, u: 0, cusum: s === "NORMAL" ? 0.3 : s === "WATCH" ? 3.5 : 7.5, status: s });
          }
          const raw_events = []; for (let h = 0; h < 24; h++) { raw_events.push({ ts: `${finding.opened_on}T${String(h).padStart(2, "0")}:10:00Z`, pump_id: pump, state: "ON", signal_id: "mock-sig" }, { ts: `${finding.opened_on}T${String(h).padStart(2, "0")}:14:00Z`, pump_id: pump, state: "OFF", signal_id: "mock-sig" }); }
          const level = Array.from({ length: 96 }, (_, i) => ({ ts: `${finding.opened_on}T${String(Math.floor(i / 4)).padStart(2, "0")}:${String((i % 4) * 15).padStart(2, "0")}:00Z`, value: 20 + 10 * Math.abs(Math.sin(i / 5)), units: "%" }));
          return send(200, { alert_id: finding.alert_id, station_id: station, pump_id: pump, origin: "REAL_REPLAY", as_of_utc: q.get("as_of_utc"), finding,
            rain: { today_mm: 0, last_72h_mm: 2.4, source: "mock" }, quality_flags: ["LONG_RUN: 2 runs capped at 3,600 s"],
            supporting: ["Capacity below normal on 3 of the last 3 days"], contradictory: ["The other pump is normal"], unavailable: ["Motor current"],
            trace, transitions: [], raw_events, level, level_signal_id: "mock-level", thresholds: { h_w: 3, h_i: 6, min_effect: -0.08 },
            work_order: { title: "Inspect pump (draft)", station_id: station, pump_id: pump, priority: "High", requested_by: "Dragonfly draft - needs human review", checks: ["Impeller clog or ragging"], evidence_alert_id: finding.alert_id, caveats: ["Not a diagnosis"] },
            provenance: prov });
        }
        send(404, { code: "UNKNOWN_STATION", message: "mock: not implemented", allowed: [] });
      });
    },
  };
}
