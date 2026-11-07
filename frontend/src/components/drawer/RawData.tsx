import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Evidence } from "../../types";

const hhmm = (ts: string) => ts.slice(11, 16);

// Section 10.4 item 5: pump on/off for the trigger day and the level trace, with signal ids and UTC times.
export function RawData({ ev }: { ev: Evidence }) {
  const pumps = [...new Set(ev.raw_events.map((e) => e.pump_id))].sort();
  const dayStart = Date.parse(`${ev.finding.opened_on}T00:00:00Z`);
  const pct = (ts: string) => (100 * (Date.parse(ts) - dayStart)) / 86_400_000;
  const units = ev.level[0]?.units ?? "";
  return (
    <section data-testid="drawer-raw-events" aria-label="Raw data for the trigger day">
      <h3 className="sub-title">Raw data, {ev.finding.opened_on} (UTC)</h3>
      {ev.raw_events.length === 0 ? <p>No pump events for this day.</p> : (
        <div className="strip" role="img" aria-label={`Pump on and off timeline, ${ev.raw_events.length} events`}>
          {pumps.map((p) => (
            <div key={p} className="strip-row">
              <span className="bar-label">{p}</span>
              <div className="strip-track">
                {ev.raw_events.filter((e) => e.pump_id === p && e.state === "ON").map((on) => {
                  const off = ev.raw_events.find((e) => e.pump_id === p && e.state === "OFF" && e.ts > on.ts);
                  return <span key={on.ts} className="strip-run" style={{ left: `${pct(on.ts)}%`, width: `${Math.max(0.3, pct(off?.ts ?? on.ts) - pct(on.ts))}%` }} />;
                })}
              </div>
            </div>
          ))}
        </div>
      )}
      {ev.level.length === 0 ? <p>No level data for this day.</p> : (
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={ev.level.map((l) => ({ t: hhmm(l.ts), v: l.value }))} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="2 4" />
            <XAxis dataKey="t" tick={{ fontSize: 11 }} minTickGap={40} />
            <YAxis tick={{ fontSize: 11 }} width={36} />
            <Tooltip />
            <Line dataKey="v" stroke="var(--chart-line)" dot={false} isAnimationActive={false} name={`Level (${units})`} />
          </LineChart>
        </ResponsiveContainer>
      )}
      <details>
        <summary>View events as table ({ev.raw_events.length})</summary>
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th scope="col">Time (UTC)</th><th scope="col">Pump</th><th scope="col">State</th><th scope="col">Signal id</th></tr></thead>
            <tbody>{ev.raw_events.map((e, i) => <tr key={i}><td>{e.ts.slice(11, 19)}</td><td>{e.pump_id}</td><td>{e.state}</td><td>{e.signal_id}</td></tr>)}</tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
