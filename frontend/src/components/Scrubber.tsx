import { useEffect, useRef, useState } from "react";
import { addDays, daysBetween, isDay } from "../dates";

export interface Range { min: string; max: string; outages: [string, string][] }

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

// Section 10.1: day stepping, 1 day/s replay, date picker, outage marks, disabled at both edges.
export function Scrubber({ day, range, onChange, skipTo }: {
  day: string; range: Range; onChange: (day: string) => void; skipTo?: (() => void) | null;
}) {
  const [playing, setPlaying] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [typed, setTyped] = useState(day);
  const dayRef = useRef(day);
  dayRef.current = day;
  const atMin = day <= range.min;
  const atMax = day >= range.max;
  const span = Math.max(1, daysBetween(range.min, range.max));
  const outage = range.outages.find(([a, b]) => day >= a && day <= b);

  useEffect(() => setTyped(day), [day]);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      const next = addDays(dayRef.current, 1);
      if (next > range.max) { setPlaying(false); setNote("End of data"); return; }
      onChange(next);
    }, 1000);
    return () => clearInterval(id);
  }, [playing, range.max, onChange]);

  useEffect(() => { if (atMax) setPlaying(false); }, [atMax]);

  const step = (n: number) => { setNote(null); onChange(addDays(day, n)); };
  const replay = () => {
    if (reducedMotion()) { if (!atMax) step(1); else setNote("End of data"); return; } // steps only on click
    setNote(null);
    setPlaying((p) => !p);
  };
  const commitTyped = () => {
    if (!isDay(typed) || typed < range.min || typed > range.max) {
      setNote(`Pick a date between ${range.min} and ${range.max}`);
      setTyped(day);
    } else { setNote(null); onChange(typed); }
  };

  return (
    <div className="scrubber" data-testid="scrubber">
      <div className="scrubber-row">
        <button className="btn-sm" data-testid="scrubber-prev" disabled={atMin} onClick={() => step(-1)}>◀ day</button>
        <button className="btn-sm" data-testid="replay-toggle" disabled={atMax && !playing} aria-pressed={playing} onClick={replay}>
          {playing ? "Pause" : "Replay 1 day/s"}
        </button>
        <button className="btn-sm" data-testid="scrubber-next" disabled={atMax} onClick={() => step(1)}>day ▶</button>
        <label className="sr-only" htmlFor="scrubber-date">Date (UTC)</label>
        <input
          id="scrubber-date" data-testid="scrubber-date" className="date-input" type="date"
          min={range.min} max={range.max} value={typed}
          onChange={(e) => setTyped(e.target.value)} onBlur={commitTyped}
          onKeyDown={(e) => { if (e.key === "Enter") commitTyped(); }}
        />
        {skipTo && <button className="btn-sm" data-testid="skip-to-investigate" onClick={skipTo}>Skip to first Investigate</button>}
      </div>
      <div className="track">
        <input
          type="range" aria-label="Scrub through days" min={0} max={span} step={1}
          value={Math.min(span, Math.max(0, daysBetween(range.min, day)))}
          onChange={(e) => { setNote(null); onChange(addDays(range.min, Number(e.target.value))); }}
        />
        {range.outages.map(([a, b]) => (
          <span key={a} className="outage-mark" data-testid="scrubber-outage-marker" aria-hidden="true" title="Source offline (real gap in the data)"
            style={{ left: `${(100 * Math.max(0, daysBetween(range.min, a))) / span}%`,
                     width: `${Math.max(0.6, (100 * (daysBetween(a, b) + 1)) / span)}%` }} />
        ))}
      </div>
      <div className="scrubber-note">
        <span data-testid="scrubber-live-date" aria-live="polite">{day}</span>
        {outage && <span> · Source offline (real gap in the data)</span>}
        {note && <span role="status" data-testid={note === "End of data" ? "scrubber-end-note" : "scrubber-range-error"}> · {note}</span>}
      </div>
    </div>
  );
}
