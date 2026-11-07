import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { addDays, toAsOf } from "./dates";
import type { StationAssessment, StationInfo, TimelineDay } from "./types";

export interface StationView {
  info: StationInfo;
  assessment: StationAssessment;
  yesterday: TimelineDay | null; // null when there is no day before the range start
}
export type Loaded =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ok"; views: StationView[] };

// One assess per station at the chosen day, plus the previous day from /api/timeline
// ("changes since yesterday"). Results for a stale day are dropped.
export function useStationData(stations: StationInfo[], day: string, scenarioId: string | null, attempt: number): Loaded {
  const [res, setRes] = useState<Loaded>({ state: "loading" });
  useEffect(() => {
    let live = true;
    setRes({ state: "loading" });
    if (!day || stations.length === 0) return;
    const prev = addDays(day, -1);
    Promise.all(
      stations.map(async (info) => {
        const [assessment, tl] = await Promise.all([
          api.assess(info.station_id, toAsOf(day), scenarioId ?? undefined),
          prev >= info.as_of_min.slice(0, 10)
            ? api.timeline(info.station_id, scenarioId, prev, prev)
            : Promise.resolve([] as TimelineDay[]),
        ]);
        return { info, assessment, yesterday: tl.find((d) => d.day === prev) ?? null };
      }),
    ).then(
      (views) => live && setRes({ state: "ok", views }),
      (e: unknown) => live && setRes({
        state: "error",
        message: e instanceof ApiError
          ? `Can't reach the Dragonfly server (HTTP ${e.status || "no response"}). ${e.message}`
          : "Can't reach the Dragonfly server.",
      }),
    );
    return () => { live = false; };
  }, [stations, day, scenarioId, attempt]);
  return res;
}
