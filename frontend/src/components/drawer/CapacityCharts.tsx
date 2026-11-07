import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { PumpState, TraceRow } from "../../types";
import { ChartBox } from "./ChartBox";

// shortcut: the Watch and Investigate lines are the section 4.14 defaults (h_w = 3, h_i = 6).
// The response does not carry them; switch to the response once it does (asked on the board).
const WATCH_LINE = 3, INVESTIGATE_LINE = 6;
const GREY = "var(--chart-line)", BAND = "var(--chart-band)", THRESH = "var(--chart-threshold)", ABNORMAL = "var(--watch-mark)";
const fmt = (v: number | null, d = 1) => (v == null ? "–" : v.toFixed(d));

// Section 10.4 items 3 and 4. Greyscale; abnormal days get a marker shape, never color alone.
export function CapacityCharts({ trace, pump }: { trace: TraceRow[]; pump: PumpState | undefined }) {
  const data = trace.map((r) => {
    // Normal band: baseline median times exp(+/-2 robust spread). Display choice, spread = base_mad in log units.
    const spread = r.base_mad == null ? 0 : 2 * 1.4826 * Math.max(r.base_mad, 0.01 / 1.4826);
    return {
      day: r.day.slice(5), ci: r.ci, base: r.base_median,
      band: r.base_median == null ? null : [r.base_median * Math.exp(-spread), r.base_median * Math.exp(spread)],
      abnormal: r.status === "WATCH" || r.status === "INVESTIGATE" ? r.ci : null,
      cusum: r.cusum,
    };
  });
  const unit = "/h";
  return (
    <>
      <ChartBox
        title="Pumping capacity per day"
        id="chart-capacity"
        columns={["Day", `Capacity (${unit})`, `Normal (${unit})`, "Running total of shortfall", "Status"]}
        rows={trace.map((r) => [r.day, fmt(r.ci), fmt(r.base_median), fmt(r.cusum), r.status])}
        note={`${unit} = how many times this pump could empty the wet well's working volume in an hour. Grey band: this pump's normal range. Triangles mark Watch or Investigate days.`}
      >
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="2 4" />
            <XAxis dataKey="day" tick={{ fontSize: 11 }} minTickGap={24} />
            <YAxis tick={{ fontSize: 11 }} width={36} />
            <Tooltip />
            <Area dataKey="band" stroke="none" fill={BAND} isAnimationActive={false} name="Normal range" />
            <Line dataKey="base" stroke={THRESH} strokeDasharray="5 4" dot={false} isAnimationActive={false} name="Normal" />
            <Line dataKey="ci" stroke={GREY} strokeWidth={2} dot={false} isAnimationActive={false} name="Capacity" />
            <Scatter dataKey="abnormal" fill={ABNORMAL} shape="triangle" isAnimationActive={false} name="Watch / Investigate day" />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartBox>
      <section className="chart-box" aria-label="Running total of shortfall">
        <h3 className="sub-title">Running total of shortfall</h3>
        <ResponsiveContainer width="100%" height={150}>
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="2 4" />
            <XAxis dataKey="day" tick={{ fontSize: 11 }} minTickGap={24} />
            <YAxis tick={{ fontSize: 11 }} width={36} />
            <Tooltip />
            <ReferenceLine y={WATCH_LINE} stroke={THRESH} strokeDasharray="5 4" label={{ value: "Watch line", fontSize: 11, position: "insideTopLeft" }} />
            <ReferenceLine y={INVESTIGATE_LINE} stroke={THRESH} strokeDasharray="2 2" label={{ value: "Investigate line", fontSize: 11, position: "insideTopLeft" }} />
            <Line dataKey="cusum" stroke={GREY} strokeWidth={2} dot={false} isAnimationActive={false} name="Running total of shortfall" />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="meta">Rain bars are not drawn: the trace carries no daily rain yet.</p>
      </section>
      <ChartBox
        title="Run time today: observed vs expected"
        id="chart-runtime"
        columns={["", "Run time (s)"]}
        rows={[["Observed", fmt(pump?.run_median_s ?? null, 0)], ["Expected at today's inflow", fmt(pump?.expected_run_s ?? null, 0)]]}
        note="Today only: the trace has no daily run times yet."
      >
        {pump?.run_median_s == null ? (
          <p>No run-time data today.</p>
        ) : (
          <RunTimeBars observed={pump.run_median_s} expected={pump.expected_run_s} />
        )}
      </ChartBox>
    </>
  );
}

function RunTimeBars({ observed, expected }: { observed: number; expected: number | null }) {
  const max = Math.max(observed, expected ?? 0) || 1;
  return (
    <div className="bars">
      {([["Observed", observed], ["Expected at today's inflow", expected]] as const).map(([label, v]) => (
        <div key={label} className="bar-row">
          <span className="bar-label">{label}</span>
          {v == null ? <span>pump would not keep up at today's inflow</span> : (
            <>
              <span className="bar" style={{ width: `${(100 * v) / max}%` }} />
              <span>{v.toFixed(0)} s</span>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
