import type { ReplayResult } from "../types";

// Section 10.5: banner while a scenario is loaded, and the failure, trip and Investigate markers as the day passes.
export function ReplayBar({ title, variant, confidence, result, day, onExit }: {
  title: string; variant: "A" | "B"; confidence: number; result: ReplayResult | null; day: string; onExit: () => void;
}) {
  const fDay = result?.failure_at?.slice(0, 10) ?? null;
  const iDay = result?.first_investigate_at?.slice(0, 10) ?? null;
  const failed = fDay != null && day >= fDay;
  const warned = iDay != null && day >= iDay;
  const warnedBeforeTrip = result?.first_investigate_at != null && result?.failure_at != null && result.first_investigate_at < result.failure_at;
  return (
    <div className="panel replay-bar" data-testid="replay-banner">
      <p><strong>Variant {variant}: assumed mechanism, assumption confidence {confidence}. Simulated, not real station data.</strong></p>
      <p className="meta">{title}. Replay runs about 30 s.</p>
      <div className="markers" data-testid="replay-output">
        {warned && <span className="tag" data-testid="investigate-marker">◆ First Investigate {result?.first_investigate_at?.slice(0, 16).replace("T", " ")} UTC</span>}
        {failed && <span className="tag" data-testid="failure-marker">✕ Failure {result?.failure_at?.slice(0, 16).replace("T", " ")} UTC</span>}
        {failed && <span className="tag" data-testid="trip-marker">Simulated: pumps stopped; level rises to the overflow marker</span>}
        {failed && result && !warnedBeforeTrip && (
          <span className="tag">In this run it did not warn before the trip. Open the evidence to see why.</span>
        )}
      </div>
      <button className="btn-sm" onClick={onExit}>Back to real replay</button>
    </div>
  );
}
