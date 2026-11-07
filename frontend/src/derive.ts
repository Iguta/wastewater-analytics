import type { Finding, Quality, Status } from "./types";
import type { StationView } from "./useStationData";

export const STATUS_WORD: Record<Status, string> = {
  NORMAL: "Normal", WATCH: "Watch", INVESTIGATE: "Investigate",
  INSUFFICIENT_EVIDENCE: "Not enough data", SOURCE_OFFLINE: "Source offline",
};
export const QUALITY_WORD: Record<Quality, string> = {
  SUFFICIENT: "Sufficient", PARTIAL: "Partial", INSUFFICIENT: "Not enough", SOURCE_OFFLINE: "Source offline",
};
const QUALITY_RANK: Quality[] = ["SUFFICIENT", "PARTIAL", "INSUFFICIENT", "SOURCE_OFFLINE"];
export const worstQuality = (qs: Quality[]): Quality =>
  qs.reduce((w, q) => (QUALITY_RANK.indexOf(q) > QUALITY_RANK.indexOf(w) ? q : w), "SUFFICIENT" as Quality);

// "Wessex 44371: P1 Investigate, P2 Normal"
export const verdict = (v: StationView) =>
  `${v.assessment.display_name}: ${v.assessment.pumps.map((p) => `${p.pump_id} ${STATUS_WORD[p.status]}`).join(", ")}`;

// "Level sensor: OK / Faulty since {ts} / No data" from the findings (no extra field in the contract).
export function levelSensorLine(v: StationView): string {
  const a = v.assessment;
  if (a.safety.some((f) => f.type === "SOURCE_SILENT")) return "Level sensor: No data";
  const fault = a.queue.find((f) => f.type === "SENSOR_FAULT");
  return fault ? `Level sensor: Faulty since ${fault.opened_on}` : "Level sensor: OK";
}

export function stormLine(v: StationView): string {
  const s = v.assessment.storm;
  if (!s) return "Storm outlook: not available (no station location in the public data)";
  return s.storm_ahead
    ? `Storm ahead: ${s.forecast_rain_48h_in} in forecast over 48 h, gusts to ${s.max_gust_48h_mph} mph (archived forecast issued ${s.issued_on}, replayed)`
    : `No storm in the 48 h forecast (archived forecast issued ${s.issued_on}, replayed)`;
}

// "Since 2022-06-02: P2 Normal → Watch" or a plain no-change line.
export function changesLine(v: StationView, prevDay: string): string {
  if (!v.yesterday) return "Changes since yesterday: not available (first day in range)";
  const diffs = v.assessment.pumps.flatMap((p) => {
    const was = v.yesterday!.pumps.find((q) => q.pump_id === p.pump_id)?.status;
    return was && was !== p.status ? [`${p.pump_id} ${STATUS_WORD[was]} → ${STATUS_WORD[p.status]}`] : [];
  });
  return diffs.length ? `Since ${prevDay}: ${diffs.join(", ")}` : `No status changes since ${prevDay}`;
}

export interface QueueItem {
  finding: Finding; view: StationView; tag: string | null; movedUp: boolean;
}

// Section 4.11: INVESTIGATE by capacity loss (largest first), then WATCH by days open. Nothing is hidden.
export function buildQueue(views: StationView[]): QueueItem[] {
  const items = views.flatMap((view) =>
    view.assessment.queue.map((finding): QueueItem => {
      const was = view.yesterday?.pumps.find((p) => p.pump_id === finding.pump_id)?.status;
      const tag = finding.days_open <= 1 ? "New today" : was === "WATCH" && finding.status === "INVESTIGATE" ? "Was Watch yesterday" : null;
      const movedUp = !!view.assessment.storm?.storm_ahead && (finding.status === "WATCH" || finding.status === "INVESTIGATE");
      return { finding, view, tag, movedUp };
    }),
  );
  const loss = (f: Finding) => -(f.change_pct ?? 0);
  return items.sort((a, b) => {
    const ia = a.finding.status === "INVESTIGATE" ? 0 : 1, ib = b.finding.status === "INVESTIGATE" ? 0 : 1;
    if (ia !== ib) return ia - ib;
    return ia === 0 ? loss(b.finding) - loss(a.finding) : b.finding.days_open - a.finding.days_open;
  });
}
