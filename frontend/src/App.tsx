import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api";
import { Drawer } from "./components/Drawer";
import { Header } from "./components/Header";
import { EmptyState, ErrorState, Loading } from "./components/ScreenState";
import { Scrubber } from "./components/Scrubber";
import type { Range } from "./components/Scrubber";
import { StationsTab } from "./components/StationsTab";
import type { QueueItem } from "./derive";
import { dayOf } from "./dates";
import type { StationInfo, StationsResponse } from "./types";
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
  const [scenarioId] = useState<string | null>(null); // set by Incidents replay (next step)
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
        message: `Can't reach the Dragonfly server${e instanceof ApiError && e.status ? ` (HTTP ${e.status})` : ""}.`,
      }),
    );
    return () => { live = false; };
  }, [attempt, scenarioId]);

  const stations = boot.state === "ok" ? boot.data.stations : null;
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
  const data = useStationData(stations ?? NO_STATIONS, day ?? "", scenarioId, attempt);
  const retry = () => setAttempt((n) => n + 1);
  const origin = stations?.[0]?.origin ?? "REAL_REPLAY";

  return (
    <>
      <Header origin={origin} asOf={day ? `${day} 00:00` : null} serverDown={boot.state === "error" && boot.down}>
        {range && day && <Scrubber day={day} range={range} onChange={changeDay} />}
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
            {boot.state === "loading" && <Loading />}
            {boot.state === "error" && <ErrorState message={boot.message} onRetry={retry} />}
            {boot.state === "ok" && !stations?.length && <EmptyState>No stations are available.</EmptyState>}
            {boot.state === "ok" && !!stations?.length && day && (
              <>
                {data.state === "loading" && <Loading />}
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
        {tab === "incidents" && <EmptyState>Incidents tab: scenario cards and replay are built next.</EmptyState>}
        {tab === "lab" && <EmptyState><span data-testid="lab-no-report">Evaluation not run yet.</span></EmptyState>}
      </main>
      {open && <Drawer item={open.item} returnTo={open.row} onClose={() => setOpen(null)} />}
    </>
  );
}
