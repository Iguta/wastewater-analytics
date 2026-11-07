import type { Status } from "../types";

// Section 10.2 (fixed). Shape + words + color: color is never the only cue.
const SPEC: Record<Status, { shape: string; text: string; cls: string }> = {
  NORMAL: { shape: "–", text: "Normal", cls: "st-normal" },                       // grey dash
  WATCH: { shape: "▲", text: "Watch: capacity is dropping", cls: "st-watch" },     // amber triangle
  INVESTIGATE: { shape: "◆", text: "Investigate: inspect this pump", cls: "st-investigate" }, // red diamond
  INSUFFICIENT_EVIDENCE: { shape: "", text: "Not enough data", cls: "st-hatch" },
  SOURCE_OFFLINE: { shape: "", text: "Source offline", cls: "st-hatch" },
};

// Section 10.2 rows with their own wording.
export const sourceOfflineText = (since: string) => `Source offline: no data since ${since}`;
export const HIGH_LEVEL_UNKNOWN = "High-level check: unknown (level sensor faulty)";

export function StatusBadge({ status, text }: { status: Status; text?: string }) {
  const s = SPEC[status];
  return (
    <span className={`status ${s.cls}`} data-status={status}>
      {s.shape && <span aria-hidden="true">{s.shape}</span>}
      <span>{text ?? s.text}</span>
    </span>
  );
}
