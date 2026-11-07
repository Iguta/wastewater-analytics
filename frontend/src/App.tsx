import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api";
import { Drawer } from "./components/Drawer";
import { Header } from "./components/Header";
import { EmptyState, ErrorState, Loading } from "./components/ScreenState";
import { Scrubber } from "./components/Scrubber";
import type { Range } from "./components/Scrubber";
import { IncidentsTab } from "./components/IncidentsTab";
import { ReplayBar } from "./components/ReplayBar";
import { StationsTab } from "./components/StationsTab";
import type { QueueItem } from "./derive";
import { dayOf, toAsOf } from "./dates";
import type { ReplayResult, ScenarioVariant, StationInfo, StationsResponse } from "./types";
import { useStationData } from "./useStationData";

type Tab = "stations" | "incidents" | "lab";
const TABS: { id: Tab; label: string }[] = [
  { id: "stations", label: "Stations" },
  { id: "incidents", label: "Incidents" },
  { id: "lab", label: "Reliability Lab" },
];
const DEFAULT_DAY = "2022-06-03"; // dev-tier day with the real 44371 precursor (labeled as dev data in the Lab)

const NO_STATIONS: StationInfo[] = [];
type Boot = { state: "loading" } | { state: "error"; message: string; down: boolean } | { state: "ok"; data: StationsResponse };

export default function App() {
  const [tab, setTab] = useState<Tab>("stations");
  const [attempt, setAttempt] = useState(0);
  const [scenario, setScenario] = useState<{ v: ScenarioVariant; title: string } | null>(null);
  const [replays, setReplays] = useState<Record<string, ReplayResult>>({});
  const [loadingCase, setLoadingCase] = useState<string | null>(null);
  const [replayError, setReplayError] = useState<string | null>(null);
  const scenarioId = scenario?.v.scenario_id ?? null;
  const [boot, setBoot] = useState<Boot>({ state: "loading" });
  const [day, setDay] = useState<string | null>(null);
  const [open, setOpen] = useState<{ item: QueueItem; row: HTMLElement | null } | null>(null);

  useEffect(() => {
    let live = true;
    setBoot({ state: "loading" });
    api.stations(scenarioId).then(
      (data) => live && setBoot({ state: "ok", data }),
      (e: unknown) => live && setBoot({
        state: "error", down: !(e instanceof ApiError) || e.status === 0 || e.status >= 500,
        message: `Can't reach the Dragonfly server (HTTP ${e instanceof ApiError && e.status ? e.status : "no response"}).`,
      }),
    );
    return () => { live = false; };
  }, [attempt, scenarioId]);

  // Ignore a station list that belongs to the previous scenario while the new one loads.
  const stations = boot.state === "ok" && boot.data.stations.every((s) => s.scenario_id === scenarioId) ? boot.data.stations : null;
  const range = useMemo<Range | null>(() => {
    if (!stations?.length) return null;
    return {
      min: dayOf([...stations.map((s) => s.as_of_min)].sort().reverse()[0]), // intersection of all station ranges
      max: dayOf([...stations.map((s) => s.as_of_max)].sort()[0]),
      outages: [...new Map(
        stations.flatMap((s) => s.outage_windows.map(([a, b]) => [dayOf(a), dayOf(b)] as [string, string])).map((w) => [w.join("/"), w] as const),
      ).values()],
    };
  }, [stations]);

  useEffect(() => {
    if (range && day === null) setDay(DEFAULT_DAY >= range.min && DEFAULT_DAY <= range.max ? DEFAULT_DAY : range.min);
  }, [range, day]);

  const changeDay = useCallback((d: string) => { setDay(d); setOpen(null); }, []);
  const startReplay = (v: ScenarioVariant, title: string) => {
    setReplayError(null);
    setLoadingCase(v.scenario_id);
    api.replay(v.scenario_id).then(
      (r) => { setReplays((m) => ({ ...m, [v.scenario_id]: r })); setScenario({ v, title }); setDay(null); setOpen(null); setTab("stations"); },
      (e: Error & { status?: number }) => setReplayError(`Can't reach the Dragonfly server (HTTP ${e.status || "no response"}).`),
    ).finally(() => setLoadingCase(null));
  };
  const exitScenario = () => { setScenario(null); setDay(null); setOpen(null); };
  const result = scenarioId ? replays[scenarioId] ?? null : null;
  const skip = result?.first_investigate_at ? () => changeDay(result.first_investigate_at!.slice(0, 10)) : null;
  const data = useStationData(stations ?? NO_STATIONS, day ?? "", scenarioId, attempt);
  const retry = () => setAttempt((n) => n + 1);
  const origin = stations?.[0]?.origin ?? "REAL_REPLAY";

  return (
    <>
      <Header origin={origin} title={scenario?.title} asOf={day ? `${day} 00:00` : null} serverDown={boot.state === "error" && boot.down}>
        {range && day && <Scrubber day={day} range={range} onChange={changeDay} skipTo={skip} />}
      </Header>
      <nav className="tabs" role="tablist" aria-label="Views">
        {TABS.map((t) => (
          <button
            key={t.id} role="tab" aria-selected={tab === t.id} data-testid={`tab-${t.id}`}
            className={`tab${tab === t.id ? " active" : ""}`} onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <main className="main">
        {tab === "stations" && (
          <>
            {scenario && day && <ReplayBar title={scenario.title} variant={scenario.v.variant} confidence={scenario.v.confidence} result={result} day={day} onExit={exitScenario} />}
            {boot.state === "loading" && <Loading onRetry={retry} />}
            {boot.state === "error" && <ErrorState message={boot.message} onRetry={retry} />}
            {boot.state === "ok" && !stations?.length && <EmptyState>No stations are available.</EmptyState>}
            {boot.state === "ok" && !!stations?.length && day && (
              <>
                {data.state === "loading" && <Loading onRetry={retry} />}
                {data.state === "error" && <ErrorState message={data.message} onRetry={retry} />}
                {data.state === "ok" && (
                  <div className={open ? "with-drawer" : undefined}>
                    <StationsTab views={data.views} day={day} onOpen={(item, row) => setOpen({ item, row })} />
                  </div>
                )}
              </>
            )}
          </>
        )}
        {tab === "incidents" && (
          <>
            {replayError && <ErrorState message={replayError} />}
            <IncidentsTab replays={replays} onReplay={startReplay} loadingCase={loadingCase} />
          </>
        )}
        {tab === "lab" && <EmptyState testId="lab-no-report">Evaluation not run yet.</EmptyState>}
      </main>
      {open && <Drawer item={open.item} asOf={toAsOf(day!)} scenarioId={scenarioId} returnTo={open.row} onClose={() => setOpen(null)} />}
    </>
  );
}
