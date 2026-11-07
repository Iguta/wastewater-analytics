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

function pumpStatus(station: string, pump: string, day: string): "NORMAL" | "WATCH" | "INVESTIGATE" {
  if (station === "44371" && pump === "P1") {
    if (day >= "2022-06-02" && day < "2022-06-11") return day >= "2022-06-03" ? "INVESTIGATE" : "WATCH";
  }
  if (station === "45078" && pump === "P3" && day >= "2022-06-01" && day <= "2022-06-05") return "WATCH";
  return "NORMAL";
}

function assess(station: string, day: string) {
  const s = STATIONS.find((x) => x.station_id === station)!;
  const pumps = s.pumps.map((p) => {
    const status = pumpStatus(station, p, day);
    return { pump_id: p, status, quality: "SUFFICIENT", ci_today: status === "NORMAL" ? 30 : 16.3, ci_baseline: 30,
      capacity_change_pct: status === "NORMAL" ? 0.4 : -46, cusum: status === "NORMAL" ? 0.2 : 7.1,
      valid_cycles: 38, runs: 41, run_median_s: 140, expected_run_s: 95 };
  });
  const queue = pumps.filter((p) => p.status !== "NORMAL").map((p, i) => ({
    alert_id: `REAL:${station}:${p.pump_id}:CAPACITY_DROP:2022-06-01`, type: "CAPACITY_DROP", pump_id: p.pump_id, status: p.status,
    priority: i + 1, opened_on: "2022-06-01", days_open: Math.max(1, Math.round((Date.parse(day) - Date.parse("2022-06-01")) / 864e5) + 1),
    observed: p.ci_today, expected: p.ci_baseline, units: "/h", change_pct: p.capacity_change_pct,
    summary: p.status === "INVESTIGATE" ? "Investigate: inspect this pump" : "Watch: capacity is dropping",
    possible_causes: [], inspection: [],
  }));
  const worst = pumps.some((p) => p.status === "INVESTIGATE") ? "INVESTIGATE" : pumps.some((p) => p.status === "WATCH") ? "WATCH" : "NORMAL";
  return { station_id: station, display_name: s.display_name, as_of_utc: day + "T00:00:00Z", origin: "REAL_REPLAY", scenario_id: null,
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
        if (u.pathname === "/health") return send(200, { status: "ok", model_version: "dragonfly-ci-v1", source_hash: hash, code_version: "mock" });
        if (u.pathname === "/stations") return send(200, { source_hash: hash, model_version: "dragonfly-ci-v1",
          stations: STATIONS.map((s) => ({ ...s, origin: "REAL_REPLAY", scenario_id: null, as_of_min: "2022-03-16T00:00:00Z", as_of_max: "2024-01-01T00:00:00Z",
            outage_windows: [["2023-08-17T10:20:00Z", "2023-08-20T12:21:00Z"]] })) });
        if (u.pathname === "/assess") return send(200, assess(q.get("station_id")!, q.get("as_of_utc")!.slice(0, 10)));
        if (u.pathname === "/timeline") {
          const out = []; for (let d = q.get("start")!; d <= q.get("end")!; d = dayAdd(d, 1)) {
            const a = assess(q.get("station_id")!, d);
            out.push({ day: d, station_status: a.status, pumps: a.pumps.map((p) => ({ pump_id: p.pump_id, status: p.status, ci: p.ci_today, base_median: p.ci_baseline, cusum: p.cusum })) });
          } return send(200, out);
        }
        send(404, { code: "UNKNOWN_STATION", message: "mock: not implemented", allowed: [] });
      });
    },
  };
}
