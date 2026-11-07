import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api";
import type { AskResult } from "../../types";

type State =
  | { s: "idle" } | { s: "pending" } | { s: "timeout" } | { s: "offline" } | { s: "error"; message: string }
  | { s: "done"; r: AskResult };

// Section 10.4 item 10. The standard explanation is always shown above; the answer here is extra.
export function AskPanel({ stationId, asOf, scenarioId }: { stationId: string; asOf: string; scenarioId: string | null }) {
  const [q, setQ] = useState("");
  const [st, setSt] = useState<State>({ s: "idle" });
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  const submit = async () => {
    const question = q.trim();
    if (!question) return;
    const ac = new AbortController();
    abort.current = ac;
    const timer = setTimeout(() => ac.abort(), 60_000);
    setSt({ s: "pending" });
    try {
      const r = await api.ask({ question, station_id: stationId, as_of_utc: asOf, ...(scenarioId ? { scenario_id: scenarioId } : {}) }, ac.signal);
      setSt({ s: "done", r });
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) setSt({ s: "offline" });
      else if (e instanceof ApiError && e.status === 504) setSt({ s: "timeout" });
      else if (e instanceof DOMException && e.name === "AbortError") setSt({ s: "timeout" });
      else setSt({ s: "error", message: e instanceof ApiError ? e.message : "Can't reach the Dragonfly server." });
    } finally { clearTimeout(timer); }
  };

  return (
    <section aria-label="Ask Dragonfly">
      <h3 className="sub-title">Ask Dragonfly</h3>
      <div className="ask-row">
        <label className="sr-only" htmlFor="ask-input">Question</label>
        <input id="ask-input" data-testid="ask-input" className="ask-input" maxLength={2000} value={q}
          disabled={st.s === "pending"} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }} placeholder="Why is this pump flagged?" />
        <button className="btn-sm" data-testid="ask-submit" disabled={st.s === "pending" || !q.trim()} onClick={submit}>Ask</button>
      </div>
      <div aria-live="polite" data-testid="ask-answer">
        {st.s === "pending" && <p>Asking… (up to 60 s)</p>}
        {st.s === "timeout" && <p>No answer in 60 s. Showing the standard explanation.</p>}
        {st.s === "offline" && <p data-testid="ask-offline">AI explanation unavailable (no API key)</p>}
        {st.s === "error" && <p>{st.message}</p>}
        {st.s === "done" && (st.r.withheld || !st.r.answer_markdown ? (
          <p data-testid="ask-withheld">AI answer withheld: it did not match the evidence</p>
        ) : (
          <>
            <p className="answer">{st.r.answer_markdown}</p>
            <p className="meta" data-testid="ask-grounding-badge">✓ Checked against evidence</p>
          </>
        ))}
      </div>
    </section>
  );
}
