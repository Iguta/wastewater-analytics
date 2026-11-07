"""Proactive-maintenance evidence log over the real replay (docs/compliance.md; designed to support CMOM
documentation, not a compliance claim).

One row per detector incident (pump CAPACITY_DROP, STATION_WIDE_CHANGE) and per station-offline day, with the
evidence, provenance, a draft work order, and BLANK human fields. It records what the detector raised and
when; it does not record that any action was taken.

Usage: python -m backend.scripts.cmom_report [year]   (default 2022, the dev tier)
Writes reports/cmom/evidence_log_<year>.csv and .json.
"""

import json
import sys
from pathlib import Path

import pandas as pd

from backend.app import data, detect, explain, features, params

OUT = Path(__file__).resolve().parents[2] / "reports" / "cmom"
HUMAN = {"acknowledged_by": "", "acknowledged_at": "", "inspected_on": "", "outcome": ""}


def rows_for(st: str, year: int, P: params.Params) -> list[dict]:
    s = data.load(st)
    t = features.daily_table(s.events, s.level, s.rain, f"{year + 1}-01-01", st)
    r = detect.run(t, P)
    y = r[r.day.dt.year == year]
    prov = {"model_version": P.version, "source_hash": s.source_hash}
    out = []
    for iid, g in y.dropna(subset=["incident_id"]).groupby("incident_id"):
        g = g.sort_values("day")
        worst = g.loc[g.capacity_change_pct.idxmin()]
        out.append(
            {
                "alert_id": iid,
                "station_id": st,
                "pump_id": worst.pump_id,
                "finding": "CAPACITY_DROP",
                "opened_on": g.day.min().date().isoformat(),
                "last_alert_day": g.day.max().date().isoformat(),
                "max_status": "INVESTIGATE" if (g.status == "INVESTIGATE").any() else "WATCH",
                "worst_capacity_change_pct": round(float(worst.capacity_change_pct), 1),
                "max_cusum": round(float(g.cusum.max()), 2),
                "quality_at_open": g.iloc[0].quality,
                "work_order": " | ".join(explain.CHECKLISTS["CAPACITY_DROP"]),
                "caveat": explain.CAVEAT,
                **prov,
                **HUMAN,
            }
        )
    sw = y.drop_duplicates("day").sort_values("day")
    on = sw.station_wide_status != "NORMAL"
    for _, g in sw[on].groupby((on != on.shift()).cumsum()[on]):
        out.append(
            {
                "alert_id": f"REAL:{st}:STATION:STATION_WIDE_CHANGE:{g.day.min().date().isoformat()}",
                "station_id": st,
                "pump_id": "",
                "finding": "STATION_WIDE_CHANGE",
                "opened_on": g.day.min().date().isoformat(),
                "last_alert_day": g.day.max().date().isoformat(),
                "max_status": "INVESTIGATE" if (g.station_wide_status == "INVESTIGATE").any() else "WATCH",
                "worst_capacity_change_pct": round(float(g.station_shared_change_pct.min()), 1),
                "max_cusum": round(float(g.station_cusum.max()), 2),
                "quality_at_open": "",
                "work_order": " | ".join(explain.CHECKLISTS["STATION_WIDE_CHANGE"]),
                "caveat": explain.CAVEAT,
                **prov,
                **HUMAN,
            }
        )
    off = y[y.quality == "SOURCE_OFFLINE"].drop_duplicates("day")
    for _, d in off.iterrows():
        out.append(
            {
                "alert_id": f"REAL:{st}:STATION:SOURCE_SILENT:{d.day.date().isoformat()}",
                "station_id": st,
                "pump_id": "",
                "finding": "SOURCE_OFFLINE_DAY",
                "opened_on": d.day.date().isoformat(),
                "last_alert_day": d.day.date().isoformat(),
                "max_status": "SOURCE_OFFLINE",
                "worst_capacity_change_pct": None,
                "max_cusum": None,
                "quality_at_open": f"{d.offline_hours:.1f} h silent",
                "work_order": "Confirm power, comms and alarm path",
                "caveat": explain.CAVEAT,
                **prov,
                **HUMAN,
            }
        )
    return out


def main(year: int = 2022) -> None:
    P = params.load()
    rows = [row for st in data.STATIONS for row in rows_for(st, year, P)]
    df = pd.DataFrame(rows).sort_values(["station_id", "opened_on", "alert_id"])
    df.insert(1, "month", df.opened_on.str[:7])
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / f"evidence_log_{year}.csv", index=False)
    doc = {
        "note": "Detector evidence log, designed to support CMOM documentation. Human fields are blank by design: "
        "the detector does not record actions taken.",
        "year": year,
        "rows": df.to_dict("records"),
    }
    (OUT / f"evidence_log_{year}.json").write_text(json.dumps(doc, indent=2, default=str) + "\n")
    print(df.groupby(["station_id", "finding"]).size().to_string())


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2022)
