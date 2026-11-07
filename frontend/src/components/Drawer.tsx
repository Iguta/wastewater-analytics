import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { QueueItem } from "../derive";
import type { Evidence, PumpState, WorkOrder } from "../types";
import { AskPanel } from "./drawer/AskPanel";
import { CapacityCharts } from "./drawer/CapacityCharts";
import { RawData } from "./drawer/RawData";
import { ErrorState, Loading } from "./ScreenState";
import { StatusBadge } from "./StatusBadge";

const STORM_PREP = "Check standby pump starts; float and alarm test; backup power fuel and battery.";
type Load = { s: "loading" } | { s: "error"; message: string } | { s: "ok"; ev: Evidence };

const workOrderText = (w: WorkOrder) =>
  [w.title, `Station ${w.station_id}${w.pump_id ? ` ${w.pump_id}` : ""} · priority ${w.priority}`, w.requested_by, "",
   "Checks:", ...w.checks.map((c) => `- ${c}`), "", "Caveats:", ...w.caveats.map((c) => `- ${c}`), "", `Evidence: ${w.evidence_alert_id}`].join("\n");

// Section 10.4, in order. Focus moves in on open; Esc closes and focus returns to the row (section 10.3).
export function Drawer({ item, asOf, scenarioId, returnTo, onClose }: {
  item: QueueItem; asOf: string; scenarioId: string | null; returnTo: HTMLElement | null; onClose: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  const [load, setLoad] = useState<Load>({ s: "loading" });
  const [attempt, setAttempt] = useState(0);
  const f = item.finding, a = item.view.assessment;
  const pump = a.pumps.find((p) => p.pump_id === f.pump_id);

  useEffect(() => { ref.current?.focus(); }, []);
  useEffect(() => {
    let live = true;
    setLoad({ s: "loading" });
    api.evidence(f.alert_id, asOf).then(
      (ev) => live && setLoad({ s: "ok", ev }),
      (e: Error & { status?: number }) => live && setLoad({ s: "error", message: `Can't load the evidence (HTTP ${e.status || "no response"}).` }),
    );
    return () => { live = false; };
  }, [f.alert_id, asOf, attempt]);

  const close = () => { onClose(); returnTo?.focus(); };
  return (
    <aside
      ref={ref} tabIndex={-1} role="dialog" aria-modal="false" aria-label={`Evidence for ${a.display_name} ${f.pump_id ?? ""}`}
      className="drawer" data-testid="drawer"
      onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } }}
    >
      <div className="drawer-head">
        <h2 className="section-title">{a.display_name} {f.pump_id}</h2>
        <button className="btn-sm" onClick={close}>Close</button>
      </div>
      <div data-testid="drawer-status-line"><StatusBadge status={f.status} /> <span>{f.summary}</span></div>
      {load.s === "loading" && <Loading onRetry={() => setAttempt((n) => n + 1)} />}
      {load.s === "error" && <ErrorState message={load.message} onRetry={() => setAttempt((n) => n + 1)} />}
      {load.s === "ok" && <Body ev={load.ev} item={item} pump={pump} asOf={asOf} scenarioId={scenarioId} />}
    </aside>
  );
}

function Body({ ev, item, pump, asOf, scenarioId }: {
  ev: Evidence; item: QueueItem; pump: PumpState | undefined; asOf: string; scenarioId: string | null;
}) {
  const a = item.view.assessment;
  const [copied, setCopied] = useState(false);
  const excluded = ev.trace[ev.trace.length - 1]?.excluded ?? {};
  const p = pump;
  const copy = async () => {
    try { await navigator.clipboard.writeText(workOrderText(ev.work_order)); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { setCopied(false); }
  };
  return (
    <>
      <p data-testid="drawer-rain-line">
        {ev.rain.last_72h_mm == null
          ? "Rain data incomplete."
          : `Rain: ${ev.rain.last_72h_mm} mm in the last 72 h. This measure is not affected by rain.`}
      </p>
      <section>
        <p data-testid="drawer-explanation">{a.explanation}</p>
        <h3 className="sub-title">Inspection checklist</h3>
        <ul data-testid="drawer-checklist">{ev.finding.inspection.map((c) => <li key={c}>{c}</li>)}</ul>
        {a.storm?.storm_ahead && (
          <div data-testid="drawer-storm-prep"><h3 className="sub-title">Storm prep</h3><p>{STORM_PREP}</p></div>
        )}
      </section>
      <CapacityCharts trace={ev.trace} pump={p} thresholds={ev.thresholds} />
      <RawData ev={ev} />
      <section data-testid="drawer-quality">
        <h3 className="sub-title">Quality</h3>
        <p>{p ? `${p.valid_cycles} of ${p.runs} runs used for the capacity measure.` : "Cycle counts not available."}</p>
        {Object.keys(excluded).length > 0 && (
          <>
            <h4 className="sub-sub">Cycles excluded today, by reason</h4>
            <ul>{Object.entries(excluded).map(([k, n]) => <li key={k}>{k}: {n}</li>)}</ul>
          </>
        )}
        {ev.quality_flags.length ? <ul>{ev.quality_flags.map((q) => <li key={q}>{q}</li>)}</ul> : <p>No data-quality flags.</p>}
      </section>
      <section data-testid="drawer-evidence">
        <h3 className="sub-title">Evidence</h3>
        <List title="Supports" items={ev.supporting} />
        <List title="Contradicts" items={ev.contradictory} />
        <List title="Not available" items={ev.unavailable} />
      </section>
      <section data-testid="provenance">
        <h3 className="sub-title">Provenance</h3>
        <dl className="kv">
          <dt>Alert id</dt><dd>{ev.alert_id}</dd>
          <dt>Origin</dt><dd>{ev.origin}</dd>
          <dt>Signal ids</dt><dd>{ev.provenance.signal_ids.join(", ") || "–"}</dd>
          <dt>Source hash</dt><dd data-testid="provenance-source-hash">{ev.provenance.source_hash}</dd>
          <dt>Model version</dt><dd data-testid="provenance-model-version">{ev.provenance.model_version}</dd>
          <dt>Code version</dt><dd>{ev.provenance.code_version}</dd>
        </dl>
      </section>
      <section data-testid="work-order">
        <h3 className="sub-title">Draft work order</h3>
        <pre className="work-order">{workOrderText(ev.work_order)}</pre>
        <button className="btn-sm" data-testid="copy-work-order" onClick={copy}>{copied ? "Copied" : "Copy"}</button>
      </section>
      <AskPanel stationId={a.station_id} asOf={asOf} scenarioId={scenarioId} />
    </>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  return <><h4 className="sub-sub">{title}</h4>{items.length ? <ul>{items.map((i) => <li key={i}>{i}</li>)}</ul> : <p className="meta">None.</p>}</>;
}
