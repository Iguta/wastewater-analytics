import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { BenchmarkKey, DevCase, EvaluationReport, Experiment, Rate, ReplayResult } from "../types";
import { EmptyState, ErrorState, Loading } from "./ScreenState";

const rate = (r: Rate) => `${r.k} of ${r.n}`;
const num = (v: number | null, d = 1) => (v == null ? "n/a" : v.toFixed(d));
const NAMES: Record<BenchmarkKey, string> = {
  A: "A: simple rule", B: "B: physics only", C: "C: Dragonfly",
  "C-persistence": "C without persistence", "C-inhibition": "C without sibling inhibition", "C-quality": "C without quality checks",
};
const MAIN: BenchmarkKey[] = ["A", "B", "C"];
const ABLATION: BenchmarkKey[] = ["C", "C-persistence", "C-inhibition", "C-quality"];
const CANNOT_KNOW = [
  "Sudden power, controller or vandalism failures, days ahead.",
  "The physical cause.",
  "A failed check valve: backflow shortens the fill and lengthens the run, so the index can hide it or mis-size it.",
  "Two pumps wearing out together at the same rate: shown only as a station-wide change, escalated by its size.",
  "VFD stations.",
  "Stations with no telemetry.",
  "Real alarm setpoints.",
];
const EXPERIMENTS: { id: Experiment; label: string; testid: string; expect: string }[] = [
  { id: "storm_test", label: "Storm test", testid: "exp-storm-test", expect: "The simple rule fires in the storm; Dragonfly stays quiet." },
  { id: "break_sensor", label: "Break the level sensor", testid: "exp-break-sensor", expect: "Sensor fault is flagged and the high-level check reads unknown." },
  { id: "cut_power", label: "Cut the power", testid: "exp-cut-power", expect: "Source offline is raised within minutes of the data going silent." },
  { id: "one_bad_day", label: "One bad day", testid: "exp-one-bad-day", expect: "A single bad day reaches Watch, then goes quiet." },
];

type Load = { s: "loading" } | { s: "none" } | { s: "error"; message: string } | { s: "ok"; r: EvaluationReport };

export function LabTab() {
  const [load, setLoad] = useState<Load>({ s: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setLoad({ s: "loading" });
    api.evaluation().then(
      (r) => live && setLoad({ s: "ok", r }),
      (e: unknown) => live && setLoad(e instanceof ApiError && e.status === 404
        ? { s: "none" }
        : { s: "error", message: `Can't reach the Dragonfly server (HTTP ${e instanceof ApiError && e.status ? e.status : "no response"}).` }),
    );
    return () => { live = false; };
  }, [attempt]);
  const retry = () => setAttempt((n) => n + 1);

  return (
    <div className="lab">
      <section className="panel">
        <h2 className="section-title">Why not just upload it to ChatGPT?</h2>
        <p>
          A chatbot can describe a spreadsheet of pump on and off times, but it has no fixed rule for when the evidence is strong
          enough to interrupt an operator, and it can answer differently each time. Dragonfly measures each pump's capacity the same way
          every time, holds back when data is missing, and shows the evidence behind every alert. The table compares it with a simple rule
          and a physics-only check on the same cases. No chatbot was tested.
        </p>
      </section>
      {load.s === "loading" && <Loading onRetry={retry} />}
      {load.s === "error" && <ErrorState message={load.message} onRetry={retry} />}
      {load.s === "none" && <EmptyState testId="lab-no-report">Evaluation not run yet.</EmptyState>}
      {load.s === "ok" && <Report r={load.r} />}
      <Experiments />
      <section className="panel" data-testid="lab-cannot-know">
        <h2 className="section-title">What the model cannot know</h2>
        <ul>{CANNOT_KNOW.map((c) => <li key={c}>{c}</li>)}</ul>
      </section>
    </div>
  );
}

function Report({ r }: { r: EvaluationReport }) {
  return (
    <>
      <p className="meta">Model {r.model_version}. Test tier scored {r.test_scored} {r.test_scored === 1 ? "time" : "times"}. Every count shows its denominator.</p>
      <BenchTable id="lab-compare-table" title="Dragonfly against two simpler checks" keys={MAIN} r={r} />
      <BenchTable id="lab-ablations" title="What each part of Dragonfly adds" keys={ABLATION} r={r} />
      <Heatmap r={r} />
      <Proxy r={r} />
    </>
  );
}

function BenchTable({ id, title, keys, r }: { id: string; title: string; keys: BenchmarkKey[]; r: EvaluationReport }) {
  return (
    <section className="panel" data-testid={id}>
      <h2 className="section-title">{title}</h2>
      <div className="table-scroll" style={{ maxHeight: "none" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Check</th><th scope="col">Degradations caught</th><th scope="col">Median lead (days)</th>
              <th scope="col">False escalations: storm</th><th scope="col">duty swap</th><th scope="col">one bad day</th>
              <th scope="col">Real alerts per pump per 6 months</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => {
              const b = r.benchmarks[k];
              return b && (
                <tr key={k}>
                  <th scope="row">{NAMES[k]}</th><td>{rate(b.caught)}</td><td>{num(b.median_lead_days)}</td>
                  <td>{rate(b.false_storm)}</td><td>{rate(b.false_duty)}</td><td>{rate(b.false_transient)}</td><td>{num(b.real_alerts_per_pump_6mo, 2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// Section 6.2: bins are shown only where n >= 20. Greyscale bar, never color alone.
function Heatmap({ r }: { r: EvaluationReport }) {
  const [table, setTable] = useState(false);
  const h = r.heatmap;
  const cell = (l: string, m: string) => h.cells.find((c) => c.loss === l && c.ramp === m);
  return (
    <section className="panel">
      <div className="chart-head">
        <h2 className="section-title">Share of degradations caught, by size of loss and how long it took</h2>
        <button className="btn-sm" data-testid="chart-table-toggle" aria-pressed={table} onClick={() => setTable((t) => !t)}>{table ? "View as grid" : "View as table"}</button>
      </div>
      <div data-testid={table ? "lab-heatmap-table" : "lab-heatmap"}>
        <table className="data-table heat">
          <thead><tr><th scope="col">Loss \ ramp</th>{h.ramp_bins.map((m) => <th key={m} scope="col">{m}</th>)}</tr></thead>
          <tbody>
            {h.loss_bins.map((l) => (
              <tr key={l}>
                <th scope="row">{l}</th>
                {h.ramp_bins.map((m) => {
                  const c = cell(l, m);
                  if (!c || c.n < 20) return <td key={m}>{c ? `n/a (only ${c.n} cases)` : "n/a"}</td>;
                  return (
                    <td key={m}>
                      <div>{c.k} of {c.n} ({Math.round((100 * c.k) / c.n)}%)</div>
                      {!table && <div className="heat-bar"><span style={{ width: `${(100 * c.k) / c.n}%` }} /></div>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Proxy({ r }: { r: EvaluationReport }) {
  return (
    <section className="panel" data-testid="lab-proxy-events">
      <h2 className="section-title">Real pump outages</h2>
      {r.proxy.map((p) => (
        <p key={p.tier}>
          Real pump outages preceded by a warning ({p.tier} tier): {p.episodes < 5 ? `n/a (only ${p.episodes} ${p.episodes === 1 ? "episode" : "episodes"})` : `${p.preceded} of ${p.episodes}`}
        </p>
      ))}
      {r.weak_labels && (
        <p>{r.weak_labels.with_precursor} of {r.weak_labels.episodes} removals gave a warning sign; we caught {r.weak_labels.warned} of them.</p>
      )}
      <p className="meta">These are pumps taken out of service, not shown to be failures. The dev tier is 2022 data. Descriptive only: no maintenance records exist to measure real precision.</p>
    </section>
  );
}

function Experiments() {
  const [cases, setCases] = useState<DevCase[] | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { api.scenarios().then((r) => setCases(r.dev_cases), () => setErr(true)); }, []);
  return (
    <section className="panel">
      <h2 className="section-title">Try it: live experiments</h2>
      <p className="meta">Each one replays a fixed development case through the same API. Simulated, not real station data.</p>
      {err && <p>Can't load the experiment cases.</p>}
      <div className="experiments">
        {EXPERIMENTS.map((e) => <Experiment key={e.id} e={e} dev={cases?.find((c) => c.experiment === e.id) ?? null} loaded={cases != null} />)}
      </div>
    </section>
  );
}

function Experiment({ e, dev, loaded }: { e: (typeof EXPERIMENTS)[number]; dev: DevCase | null; loaded: boolean }) {
  const [st, setSt] = useState<{ s: "idle" } | { s: "run" } | { s: "err"; m: string } | { s: "ok"; r: ReplayResult }>({ s: "idle" });
  const run = () => {
    if (!dev) return;
    setSt({ s: "run" });
    api.replay(dev.case_id).then((r) => setSt({ s: "ok", r }), (x: Error & { status?: number }) => setSt({ s: "err", m: `Can't reach the Dragonfly server (HTTP ${x.status || "no response"}).` }));
  };
  return (
    <div className="experiment" data-experiment={e.id}>
      <button className="btn" data-testid={e.testid} disabled={!dev || st.s === "run"} onClick={run}>{st.s === "run" ? "Running…" : e.label}</button>
      <p className="meta">{e.expect}{loaded && !dev ? " (No case is marked for this experiment yet.)" : ""}</p>
      <div aria-live="polite">
        {st.s === "err" && <p>{st.m}</p>}
        {st.s === "ok" && <Result id={e.id} r={st.r} />}
      </div>
    </div>
  );
}

function Result({ id, r }: { id: Experiment; r: ReplayResult }) {
  const b = r.benchmarks;
  const line = (k: string, name: string) => b[k] && <li>{name}: {b[k].incident_opens === 0 ? "stayed quiet" : `raised ${b[k].incident_opens} Investigate ${b[k].incident_opens === 1 ? "alert" : "alerts"}`}</li>;
  const states = [...new Set(r.timeline.map((d) => d.station_status))];
  return (
    <div className="result">
      <p className="meta">Case {r.case_id} (simulated)</p>
      {id === "storm_test" && <ul>{line("A", "Simple rule")}{line("B", "Physics only")}{line("C", "Dragonfly")}</ul>}
      {id === "break_sensor" && (
        <p>{r.sensor_fault_flagged ? "Sensor fault flagged. High-level check: unknown (level sensor faulty)." : "No sensor fault was flagged in this run."}</p>
      )}
      {id === "cut_power" && (
        <p>{r.source_offline_after_min != null ? `Source offline raised ${r.source_offline_after_min} min after the data went silent.` : "Source offline was not raised in this run."}</p>
      )}
      {id === "one_bad_day" && <p>Station status across the window: {states.join(", ").toLowerCase().replace(/_/g, " ")}.</p>}
      <details>
        <summary>View days as table</summary>
        <div className="table-scroll"><table className="data-table"><tbody>{r.timeline.map((d) => <tr key={d.day}><td>{d.day}</td><td>{d.station_status}</td></tr>)}</tbody></table></div>
      </details>
    </div>
  );
}
