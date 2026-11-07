import type { Origin } from "../types";

// Section 10.1: product name, always-visible origin badge, "Data up to ..." label (never "now").
const ORIGIN_TEXT: Record<Origin, string> = {
  REAL_REPLAY: "REPLAY · Wessex Water telemetry 2022–2023 (CC BY) · not live data",
  SYNTHETIC_INJECTION: "SIMULATION · synthetic fault in real telemetry · not real station data",
  SIMULATED_INCIDENT: "SIMULATION · scenario · not real station data",
};

export function Header({ origin, asOf, serverDown }: { origin: Origin; asOf: string | null; serverDown: boolean }) {
  return (
    <>
      {serverDown && <div data-testid="server-banner" role="alert" className="banner">Server not reachable</div>}
      <header className="header">
        <strong className="brand">Dragonfly AI</strong>
        <span data-testid="origin-badge" className="origin">{ORIGIN_TEXT[origin]}</span>
        <span data-testid="as-of-label" className="asof">{asOf ? `Data up to ${asOf} UTC` : "Data up to –"}</span>
        {/* Scrubber controls (◀ day, Replay, day ▶, date picker) are added once /api/stations defines the range. */}
      </header>
    </>
  );
}
