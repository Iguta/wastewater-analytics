import type { ReactNode } from "react";
import type { Origin } from "../types";

// Section 10.1: product name, always-visible origin badge, "Data up to ..." label (never "now").
const ORIGIN_TEXT: Record<Origin, string> = {
  REAL_REPLAY: "REPLAY · Wessex Water telemetry 2022–2023 (CC BY) · not live data",
  SYNTHETIC_INJECTION: "SIMULATION · synthetic fault in real telemetry · not real station data",
  SIMULATED_INCIDENT: "SIMULATION · scenario · not real station data", // replaced by the scenario title when known
};

export function Header({ origin, asOf, serverDown, title, children }: { origin: Origin; asOf: string | null; serverDown: boolean; title?: string; children?: ReactNode }) {
  return (
    <>
      {serverDown && <div data-testid="server-banner" role="alert" className="banner">Server not reachable</div>}
      <header className="header">
        <strong className="brand">Dragonfly AI</strong>
        <span data-testid="origin-badge" className="origin">{origin === "SIMULATED_INCIDENT" && title ? `SIMULATION · ${title} · not real station data` : ORIGIN_TEXT[origin]}</span>
        <span data-testid="as-of-label" className="asof">{asOf ? `Data up to ${asOf} UTC` : "Data up to –"}</span>
        {children}
      </header>
    </>
  );
}
