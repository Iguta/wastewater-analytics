import { useState } from "react";
import { addDays } from "../dates";
import { buildQueue, changesLine, levelSensorLine, QUALITY_WORD, STATUS_WORD, stormLine, verdict, worstQuality } from "../derive";
import type { QueueItem } from "../derive";
import type { Finding } from "../types";
import type { StationView } from "../useStationData";
import { StatusBadge } from "./StatusBadge";

const TOP_N = 5;

export function StationsTab({ views, day, onOpen }: {
  views: StationView[]; day: string; onOpen: (item: QueueItem, row: HTMLElement | null) => void;
}) {
  const prev = addDays(day, -1);
  const queue = buildQueue(views);
  const safety = views.flatMap((v) => v.assessment.safety.map((f) => ({ f, v })));
  return (
    <div className="stations-grid">
      <section aria-label="Stations" className="tiles">
        {views.map((v) => <StationTile key={v.info.station_id} v={v} prev={prev} />)}
      </section>
      <div className="right-col">
        <SafetyStrip items={safety} />
        <AttentionQueue queue={queue} views={views} day={day} onOpen={onOpen} />
      </div>
    </div>
  );
}

function StationTile({ v, prev }: { v: StationView; prev: string }) {
  const a = v.assessment;
  const warming = a.missing_evidence.some((m) => /warming up/i.test(m));
  return (
    <article className="panel tile" data-testid="station-tile" data-station-id={a.station_id}>
      <h2 className="tile-title" data-testid="station-verdict">{verdict(v)}</h2>
      <div className="chips">
        {a.pumps.map((p) => (
          <span key={p.pump_id} data-testid="pump-chip" data-pump-id={p.pump_id} data-status={p.status}>
            <StatusBadge status={p.status} text={`${p.pump_id} ${STATUS_WORD[p.status]}${p.status === "INSUFFICIENT_EVIDENCE" && warming ? " (warming up)" : ""}`} />
          </span>
        ))}
      </div>
      <p className="meta">Data up to {a.as_of_utc.replace("T", " ").replace(/:00Z$/, "")} UTC</p>
      <p className="meta">Evidence: {QUALITY_WORD[a.quality]}</p>
      <p className="meta" data-testid="level-sensor-line">{levelSensorLine(v)}</p>
      <p className="meta" data-testid="changes-since-yesterday">{changesLine(v, prev)}</p>
      <p className="meta" data-testid="storm-line">{stormLine(v)}</p>
    </article>
  );
}

function SafetyStrip({ items }: { items: { f: Finding; v: StationView }[] }) {
  return (
    <section className="panel" data-testid="safety-strip" aria-label="Safety strip">
      <h2 className="section-title">Safety (SCADA-equivalent checks)</h2>
      {items.length === 0 ? (
        <p data-testid="safety-empty">No safety findings. SCADA-equivalent checks; real setpoints unknown.</p>
      ) : (
        <ul className="plain-list">
          {items.map(({ f, v }) => (
            <li key={f.alert_id} className="safety-item">
              <StatusBadge status={f.status} text={f.type === "SOURCE_SILENT" ? `Source offline: ${f.summary}` : `Investigate: ${f.summary}`} />
              <span> {v.assessment.display_name}{f.type === "HIGH_LEVEL" && " · SCADA-equivalent; real setpoints unknown."}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function AttentionQueue({ queue, views, day, onOpen }: {
  queue: QueueItem[]; views: StationView[]; day: string; onOpen: (i: QueueItem, row: HTMLElement | null) => void;
}) {
  const [showLow, setShowLow] = useState(false);
  const top = queue.slice(0, TOP_N), low = queue.slice(TOP_N);
  const q = worstQuality(views.map((v) => v.assessment.quality));
  return (
    <section className="panel" data-testid="attention-queue" aria-label="Attention queue">
      <h2 className="section-title">Attention queue</h2>
      {queue.length === 0 ? (
        <p data-testid="queue-empty">
          {q === "SUFFICIENT"
            ? `No pumps need attention as of ${day}.`
            : `Nothing flagged, but evidence is ${QUALITY_WORD[q]}.`}
        </p>
      ) : (
        <>
          <QueueTable items={top} total={queue.length} offset={0} onOpen={onOpen} />
          {low.length > 0 && (
            <>
              <button className="btn-sm" data-testid="low-priority-toggle" aria-expanded={showLow} onClick={() => setShowLow((s) => !s)}>
                Low priority ({low.length})
              </button>
              {showLow && <QueueTable items={low} total={queue.length} offset={TOP_N} onOpen={onOpen} />}
            </>
          )}
        </>
      )}
    </section>
  );
}

function QueueTable({ items, total, offset, onOpen }: {
  items: QueueItem[]; total: number; offset: number; onOpen: (i: QueueItem, row: HTMLElement | null) => void;
}) {
  return (
    <table className="queue">
      <thead className="sr-only">
        <tr><th>Rank</th><th>Pump</th><th>Capacity change</th><th>Evidence</th><th>Status</th></tr>
      </thead>
      <tbody>
        {items.map((it, i) => {
          const f = it.finding;
          const open = (e: { currentTarget: HTMLElement }) => onOpen(it, e.currentTarget);
          return (
            <tr
              key={f.alert_id} tabIndex={0} className="queue-row" data-testid="queue-row"
              data-alert-id={f.alert_id} data-status={f.status}
              onClick={open} onKeyDown={(e) => { if (e.key === "Enter") open(e); }}
            >
              <td className="rank">{offset + i + 1} of {total}</td>
              <td>
                <strong>{it.view.assessment.display_name}{f.pump_id ? ` ${f.pump_id}` : ""}</strong>
                <div className="meta">{f.summary}</div>
                <div className="meta">Opened {f.opened_on} · flagged {f.days_open} {f.days_open === 1 ? "day" : "days"}</div>
                <div className="tags">
                  {it.tag && <span className="tag" data-testid="queue-tag">{it.tag}</span>}
                  {it.movedUp && (
                    <span className="tag" data-testid="queue-moved-up"
                      title={`Forecast: ${it.view.assessment.storm?.forecast_rain_48h_in} in rain and gusts to ${it.view.assessment.storm?.max_gust_48h_mph} mph over 48 h`}>
                      Moved up: storm ahead
                    </span>
                  )}
                </div>
              </td>
              <td>{f.change_pct == null ? "–" : `${f.change_pct > 0 ? "+" : ""}${f.change_pct.toFixed(0)}%`}</td>
              <td>Evidence: {QUALITY_WORD[it.view.assessment.quality]}</td>
              <td><StatusBadge status={f.status} /></td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
