import { Area, Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { PumpState, TraceRow } from "../../types";
import { ChartBox } from "./ChartBox";

const GREY = "var(--chart-line)", BAND = "var(--chart-band)", THRESH = "var(--chart-threshold)", ABNORMAL = "var(--watch-mark)";
const fmt = (v: number | null, d = 1) => (v == null ? "–" : v.toFixed(d));

// Section 10.4 items 3 and 4. Greyscale; abnormal days get a marker shape, never color alone.
export function CapacityCharts({ trace, pump, thresholds }: { trace: TraceRow[]; pump: PumpState | undefined; thresholds: { h_w: number; h_i: number } }) {
  const data = trace.map((r) => {
    // Normal band: baseline median times exp(+/-2 robust spread). Display choice, spread = base_mad in log units.
    const spread = r.base_mad == null ? 0 : 2 * 1.4826 * Math.max(r.base_mad, 0.01 / 1.4826);
    return {
      day: r.day.slice(5), ci: r.ci, base: r.base_median,
      band: r.base_median == null ? null : [r.base_median * Math.exp(-spread), r.base_median * Math.exp(spread)],
      abnormal: r.status === "WATCH" || r.status === "INVESTIGATE" ? r.ci : null,
      cusum: r.cusum, rain: r.rain_mm,
    };
  });
  const unit = "/h";
  return (
    <>
      <ChartBox
        title="Pumping capacity per day"
        id="chart-capacity"
        columns={["Day", `Capacity (${unit})`, `Normal (${unit})`, "Running total of shortfall", "Rain (mm)", "Status"]}
        rows={trace.map((r) => [r.day, fmt(r.ci), fmt(r.base_median), fmt(r.cusum), fmt(r.rain_mm), r.status])}
        note={`${unit} = how many times this pump could empty the wet well's working volume in an hour. Grey band: this pump's normal range. Triangles mark Watch or Investigate days. Bars: daily rain.`}
      >
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="2 4" />
            <XAxis dataKey="day" tick={{ fontSize: 11 }} minTickGap={24} />
            <YAxis yAxisId="ci" tick={{ fontSize: 11 }} width={36} />
            <YAxis yAxisId="rain" orientation="right" tick={{ fontSize: 11 }} width={30} />
            <Tooltip />
            <Bar yAxisId="rain" dataKey="rain" fill="var(--chart-rain)" barSize={3} isAnimationActive={false} name="Rain (mm)" />
            <Area yAxisId="ci" dataKey="band" stroke="none" fill={BAND} isAnimationActive={false} name="Normal range" />
            <Line yAxisId="ci" dataKey="base" stroke={THRESH} strokeDasharray="5 4" dot={false} isAnimationActive={false} name="Normal" />
            <Line yAxisId="ci" dataKey="ci" stroke={GREY} strokeWidth={2} dot={false} isAnimationActive={false} name="Capacity" />
            <Scatter yAxisId="ci" dataKey="abnormal" fill={ABNORMAL} shape="triangle" isAnimationActive={false} name="Watch / Investigate day" />
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
            <ReferenceLine y={thresholds.h_w} stroke={THRESH} strokeDasharray="5 4" label={{ value: "Watch line", fontSize: 11, position: "insideTopLeft" }} />
            <ReferenceLine y={thresholds.h_i} stroke={THRESH} strokeDasharray="2 2" label={{ value: "Investigate line", fontSize: 11, position: "insideTopLeft" }} />
            <Line dataKey="cusum" stroke={GREY} strokeWidth={2} dot={false} isAnimationActive={false} name="Running total of shortfall" />
          </ComposedChart>
        </ResponsiveContainer>
      </section>
      <ChartBox
        title="Run time per day: observed vs expected"
        id="chart-runtime"
        columns={["Day", "Observed (s)", "Expected at that day's inflow (s)"]}
        rows={trace.map((r) => [r.day, fmt(r.run_median_s, 0), fmt(r.expected_run_s, 0)])}
        note="Expected = how long a run should take at that day's inflow if the pump were at its normal capacity."
      >
        {trace.some((r) => r.run_median_s != null) ? (
          <ResponsiveContainer width="100%" height={170}>
            <ComposedChart data={trace.map((r) => ({ day: r.day.slice(5), observed: r.run_median_s, expected: r.expected_run_s }))} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="2 4" />
              <XAxis dataKey="day" tick={{ fontSize: 11 }} minTickGap={24} />
              <YAxis tick={{ fontSize: 11 }} width={36} />
              <Tooltip />
              <Line dataKey="expected" stroke={THRESH} strokeDasharray="5 4" dot={false} isAnimationActive={false} name="Expected" />
              <Line dataKey="observed" stroke={GREY} strokeWidth={2} dot={false} isAnimationActive={false} name="Observed" />
            </ComposedChart>
          </ResponsiveContainer>
        ) : pump?.run_median_s == null ? (
          <p>No run-time data.</p>
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
