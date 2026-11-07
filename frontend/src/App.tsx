import { useEffect, useState } from "react";
import { api } from "./api";
import { Header } from "./components/Header";
import { EmptyState, ErrorState, Loading } from "./components/ScreenState";

type Tab = "stations" | "incidents" | "lab";
const TABS: { id: Tab; label: string }[] = [
  { id: "stations", label: "Stations" },
  { id: "incidents", label: "Incidents" },
  { id: "lab", label: "Reliability Lab" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("stations");
  const [health, setHealth] = useState<"loading" | "ok" | "down">("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setHealth("loading");
    api.health().then(() => setHealth("ok"), () => setHealth("down"));
  }, [attempt]);

  return (
    <>
      <Header origin="REAL_REPLAY" asOf={null} serverDown={health === "down"} />
      <nav className="tabs" role="tablist" aria-label="Views">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            data-testid={`tab-${t.id === "lab" ? "lab" : t.id}`}
            className={`tab${tab === t.id ? " active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <main className="main">
        {health === "loading" && <Loading />}
        {health === "down" && (
          <ErrorState message="Can't reach the Dragonfly server. Start it with `make serve`." onRetry={() => setAttempt((n) => n + 1)} />
        )}
        {health === "ok" && (
          <EmptyState>
            {tab === "stations" && "Stations tab: tiles, safety strip and attention queue are built next."}
            {tab === "incidents" && "Incidents tab: scenario cards and replay are built next."}
            {tab === "lab" && "Evaluation not run yet."}
          </EmptyState>
        )}
      </main>
    </>
  );
}
