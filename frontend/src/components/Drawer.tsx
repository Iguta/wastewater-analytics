import { useEffect, useRef } from "react";
import type { QueueItem } from "../derive";
import { StatusBadge } from "./StatusBadge";

// Shell only: focus moves in on open, Esc closes and focus returns to the row (section 10.3).
// The evidence sections (section 10.4) are added next.
export function Drawer({ item, returnTo, onClose }: { item: QueueItem; returnTo: HTMLElement | null; onClose: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  const close = () => { onClose(); returnTo?.focus(); };
  const f = item.finding;
  return (
    <aside
      ref={ref} tabIndex={-1} role="dialog" aria-modal="false" aria-label={`Evidence for ${item.view.assessment.display_name} ${f.pump_id ?? ""}`}
      className="drawer" data-testid="drawer"
      onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } }}
    >
      <div className="drawer-head">
        <h2 className="section-title">{item.view.assessment.display_name} {f.pump_id}</h2>
        <button className="btn-sm" onClick={close}>Close</button>
      </div>
      <p data-testid="drawer-status-line"><StatusBadge status={f.status} /> {f.summary}</p>
    </aside>
  );
}
