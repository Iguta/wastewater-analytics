import { useState } from "react";
import type { ReactNode } from "react";

// Every chart has a "View as table" toggle as its text alternative (section 10.4).
export function ChartBox({ title, id, columns, rows, children, note }: {
  title: string; id: "chart-capacity" | "chart-runtime"; columns: string[]; rows: (string | number)[][];
  children: ReactNode; note?: string;
}) {
  const [table, setTable] = useState(false);
  return (
    <section className="chart-box" aria-label={title}>
      <div className="chart-head">
        <h3 className="sub-title">{title}</h3>
        <button className="btn-sm" data-testid="chart-table-toggle" aria-pressed={table} onClick={() => setTable((t) => !t)}>
          {table ? "View as chart" : "View as table"}
        </button>
      </div>
      {table ? (
        <div className="table-scroll" data-testid={`${id}-table`}>
          <table className="data-table">
            <thead><tr>{columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
            <tbody>{rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : (
        <div data-testid={id}>{children}</div>
      )}
      {note && <p className="meta">{note}</p>}
    </section>
  );
}
