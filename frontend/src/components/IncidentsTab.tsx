import { useEffect, useState } from "react";
import { api, errorText } from "../api";
import type { ReplayResult, ScenarioCard, ScenarioFact, ScenarioVariant } from "../types";
import { ErrorState, Loading } from "./ScreenState";

const DETECT_LINE: Record<ScenarioVariant["detectability"], string> = {
  PREDICTABLE_DAYS_AHEAD: "Warning days ahead is possible (variant A only)",
  DETECTABLE_AT_ONSET: "Detects the moment it happens; cannot predict it",
  NOT_DETECTABLE: "Not detectable from this data",
};
const fmtTs = (ts: string | null) => (ts ? ts.replace("T", " ").replace(/:00Z$/, "") + " UTC" : "none");
const gal = (n: number) => `Simulated: ${n.toLocaleString("en-US")} gal`;
// Section 10.5 captions: the response policy assumed for each scenario.
const CAPTION: Record<string, string> = {
  bloomington_morningside_2024_04_11: "Assumes the repair finishes R h after the first Investigate; every other step as recorded.",
  fishers_bowline_2009_01_20: "Assumes discovery takes the listed time after the failure; every other step as recorded.",
};

export function IncidentsTab({ replays, onReplay, loadingCase }: {
  replays: Record<string, ReplayResult>; onReplay: (v: ScenarioVariant, title: string) => void; loadingCase: string | null;
}) {
  const [state, setState] = useState<{ s: "loading" } | { s: "error"; message: string } | { s: "ok"; cards: ScenarioCard[] }>({ s: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setState({ s: "loading" });
    api.scenarios().then(
      (r) => live && setState({ s: "ok", cards: r.scenarios }),
      (e: unknown) => live && setState({ s: "error", message: errorText(e) }),
    );
    return () => { live = false; };
  }, [attempt]);

  if (state.s === "loading") return <Loading onRetry={() => setAttempt((n) => n + 1)} />;
  if (state.s === "error") return <ErrorState message={state.message} onRetry={() => setAttempt((n) => n + 1)} />;
  return <div className="cards">{state.cards.map((c) => <Card key={c.id} card={c} replays={replays} onReplay={onReplay} loadingCase={loadingCase} />)}</div>;
}

function Chip({ f }: { f: ScenarioFact }) {
  return (
    <li className="fact">
      <span className="fact-label">{f.label}:</span> <span>{f.value}{/\bgal(lons)?\b/i.test(f.value) && !/\(record\)/i.test(f.value) ? " (record)" : ""}</span>{" "}
      <span className="tag" data-testid="fact-chip" data-verified={f.status === "VERIFIED"}>{f.status}</span>
      {f.source && <span className="meta"> {f.source_url ? <a href={f.source_url}>{f.source}</a> : f.source}</span>}
    </li>
  );
}

function Card({ card, replays, onReplay, loadingCase }: {
  card: ScenarioCard; replays: Record<string, ReplayResult>; onReplay: (v: ScenarioVariant, title: string) => void; loadingCase: string | null;
}) {
  return (
    <article className="panel" data-testid="incident-card" data-scenario-id={card.id}>
      <h2 className="section-title">{card.title}</h2>
      <h3 className="sub-title">What happened (the record)</h3>
      <ul className="plain-list">{card.facts.map((f) => <Chip key={f.label} f={f} />)}</ul>
      <h3 className="sub-title">What failed (assumed mechanism, two variants)</h3>
      <div className="variants">
        {card.variants.map((v) => (
          <section key={v.variant} className="variant" data-testid="variant-card" data-variant={v.variant}>
            <h4 className="sub-sub">Variant {v.variant}</h4>
            <p><strong>{v.name}</strong></p>
            <p className="meta">Assumption confidence {v.confidence}. {v.reason}</p>
            <p className="meta">{DETECT_LINE[v.detectability]}</p>
            <button className="btn" data-testid={`replay-variant-${v.variant.toLowerCase()}`} disabled={loadingCase === v.scenario_id} onClick={() => onReplay(v, card.title)}>
              {loadingCase === v.scenario_id ? "Loading…" : `Replay variant ${v.variant}`}
            </button>
          </section>
        ))}
      </div>
      <h3 className="sub-title">What Dragonfly detected, and when</h3>
      {card.variants.every((v) => !replays[v.scenario_id]) && <p className="meta">Run a replay to see the result here.</p>}
      {card.variants.map((v) => replays[v.scenario_id] && <Outcome key={v.variant} v={v} r={replays[v.scenario_id]} cardId={card.id} />)}
      <h3 className="sub-title">What the record says about the outcome</h3>
      <ul className="plain-list">{card.outcome_facts.map((f) => <Chip key={f.label} f={f} />)}</ul>
    </article>
  );
}

function Outcome({ v, r, cardId }: { v: ScenarioVariant; r: ReplayResult; cardId: string }) {
  const [truth, setTruth] = useState(false);
  const o = r.outcome;
  const noWorse = o != null && o.with_dragonfly_gal === o.no_warning_gal;
  return (
    <div className="outcome" data-testid="outcome-row" data-variant={v.variant}>
      <h4 className="sub-sub">Variant {v.variant}</h4>
      <dl className="kv">
        <dt>First Watch</dt><dd>{fmtTs(r.first_watch_at)}</dd>
        <dt>First Investigate</dt><dd>{fmtTs(r.first_investigate_at)}</dd>
        <dt>Failure</dt><dd>{fmtTs(r.failure_at)}</dd>
        <dt>Lead time</dt><dd>{r.lead_time_h == null ? "none" : `${r.lead_time_h} h before the trip`}</dd>
      </dl>
      {o ? (
        <>
          <p data-testid="simulated-gal">No warning: {gal(o.no_warning_gal)}</p>
          {cardId.startsWith("bloomington") && v.variant === "B" ? (
            <p>No improvement: the station alarm is assumed to have worked.</p>
          ) : (
            <>
              <div className="sens">
                {o.sensitivity.map((s) => (
                  <div key={s.label} className="sens-cell"><span className="meta">{s.label}</span><span data-testid="simulated-gal">{gal(s.simulated_gal)}</span></div>
                ))}
              </div>
              {noWorse && <p className="meta">With Dragonfly: same as no warning under these assumptions.</p>}
              <p className="meta">{CAPTION[cardId]}</p>
            </>
          )}
          <ul className="meta">{o.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
        </>
      ) : <p className="meta">No overflow simulation for this case.</p>}
      <button className="btn-sm" data-testid="reveal-truth" aria-expanded={truth} onClick={() => setTruth((t) => !t)}>
        {truth ? "Hide simulation ground truth" : "Reveal simulation ground truth"}
      </button>
      {truth && <pre className="work-order">{JSON.stringify(r.truth, null, 2)}</pre>}
    </div>
  );
}
