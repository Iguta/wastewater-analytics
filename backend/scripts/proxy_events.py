"""Real "pump out of service" proxy events (ARCHITECTURE.md §5.7).

MEASUREMENT ONLY. These are weak, unlabeled proxies (a removal is not a failure). They are never used for
tuning or for choosing any parameter.

Episode: a pump whose trailing baseline median is >= 10 runs/day has 0 runs for >= 2 consecutive days while a
sibling has >= 10 runs on every episode day. Tier = year (2022 dev, 2023 test).
Preceded: a CAPACITY_DROP incident (WATCH or INVESTIGATE) opened >= 1 day before the episode start and active
within the 14 days before it. PUMP_NOT_RUNNING never counts.

Usage:
  python -m backend.scripts.proxy_events                  # the 3 model stations, from fixtures
  WESSEX_DIR=... python -m backend.scripts.proxy_events --all-stations
Only the 2022 (dev) summary is printed; 2023 results go to the JSON file only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd

from backend.app import data, detect, features, params, quality

BUSY = 10
MIN_DAYS = 2
LOOKBACK_DAYS = 14
ROTATION_STATIONS = {"44372"}  # duty rotation, not failures: reported separately, excluded from totals
END = "2024-01-01T00:00:00Z"
OUT = Path(__file__).resolve().parents[2] / "reports"


def episodes(r: pd.DataFrame) -> list[dict]:
    """Find episodes in a detect.run output (needs pump_id, day, runs, base_runs_median, incident_id)."""
    sib = r.groupby("day")["runs"].transform("max")  # max over all pumps; the pump itself has 0 runs
    cand = (r["base_runs_median"] >= BUSY) & (r["runs"] == 0) & (sib >= BUSY)
    out = []
    for pump, g in r.assign(cand=cand).sort_values("day").groupby("pump_id"):
        g = g.reset_index(drop=True)
        block = (g["cand"] != g["cand"].shift()).cumsum()
        for _, b in g[g["cand"]].groupby(block[g["cand"]]):
            if len(b) < MIN_DAYS or (b["day"].diff().dt.days.fillna(1) != 1).any():
                continue
            start, end = b["day"].min(), b["day"].max()
            before = g[(g["day"] >= start - pd.Timedelta(days=LOOKBACK_DAYS)) & (g["day"] < start)]
            ids = before["incident_id"].dropna()
            opened = [pd.Timestamp(i.rsplit(":", 1)[1]) for i in ids if ":CAPACITY_DROP:" in i]
            opened = [o for o in opened if o <= start - pd.Timedelta(days=1)]
            first = min(opened) if opened else None
            out.append(
                {
                    "station": str(r["station_id"].iloc[0]),
                    "pump": pump,
                    "start": start.date().isoformat(),
                    "end": end.date().isoformat(),
                    "tier": "dev"
                    if start.year == 2022
                    else "test"
                    if start.year == 2023
                    else str(start.year),
                    "preceded": first is not None,
                    "first_alert_day": first.date().isoformat() if first is not None else None,
                    "lead_days": int((start - first).days) if first is not None else None,
                    # stricter than §5.7: a warning opened 1-14 days ahead, not an incident open for months
                    "timely": first is not None and (start - first).days <= LOOKBACK_DAYS,
                }
            )
    return out


def run_station(station_id: str, events: pd.DataFrame, level=None, rain=None) -> list[dict]:
    level = (
        level
        if level is not None
        else pd.DataFrame(columns=["signal_id", "ts", "value", "units", "in_range"])
    )
    rain = (
        rain if rain is not None else pd.DataFrame({"ts_hour": pd.Series(dtype="datetime64[ns]"), "mm": []})
    )
    t = features.daily_table(events, level, rain, END, station_id)
    if t.empty:
        return []
    if level.empty:
        # shortcut: all-station mode has no level stream, so ordinary >10 min gaps between pump events would
        # count as silence; use 6 h of pump-event silence instead. Upgrade: load level for all 24 stations.
        first, last = t["day"].min(), t["day"].max() + pd.Timedelta(days=1)
        off = features.offline_hours_by_day(events["ts"], first, last, pd.Timedelta(hours=6))
        t["offline_hours"] = t["day"].map(off).fillna(0.0)
        t["quality"] = t.apply(features.day_quality, axis=1)
    return episodes(detect.run(t, params.load()))


def summarize(eps: list[dict], tier: str) -> str:
    e = [x for x in eps if x["tier"] == tier]
    if len(e) < 5:
        return f"n/a (n={len(e)})"
    pre = [x for x in e if x["preceded"]]
    leads = sorted(x["lead_days"] for x in pre)
    med = leads[len(leads) // 2] if leads else None
    timely = sum(x["timely"] for x in e)
    return (
        f"{len(e)} episodes, {len(pre)} preceded by an open capacity-drop incident (median lead {med} d), "
        f"{timely} by a warning opened 1-{LOOKBACK_DAYS} d ahead"
    )


def main(argv: list[str]) -> None:
    all_eps: list[dict] = []
    if "--all-stations" in argv:
        raw = pd.read_csv(Path(os.environ["WESSEX_DIR"]).expanduser() / "sps-run-stop-data.csv", dtype=str)
        raw.columns = ["signal_id", "ts", "value"]
        raw["station"] = raw["signal_id"].str.split("_").str[0]
        for st, g in raw.groupby("station"):
            ev = quality.parse_events(g[["signal_id", "ts", "value"]], {})
            all_eps += run_station(st, ev)
        name = "proxy_events_all_stations.json"
    else:
        for st in data.STATIONS:
            s = data.load(st)
            all_eps += run_station(st, s.events, s.level, s.rain)
        name = "proxy_events.json"
    headline = [x for x in all_eps if x["station"] not in ROTATION_STATIONS]
    rotation = [x for x in all_eps if x["station"] in ROTATION_STATIONS]
    report = {
        "note": "Measurement only: weak proxies for 'pump out of service', never used for tuning (§5.7).",
        "definition": f"busy pump (baseline >= {BUSY} runs/day) at 0 runs for >= {MIN_DAYS} days, sibling >= {BUSY} "
        f"runs every episode day; preceded = CAPACITY_DROP opened >= 1 d before, active within {LOOKBACK_DAYS} d",
        "rotation_stations_excluded": sorted(ROTATION_STATIONS),
        "counts": {
            tier: {
                "episodes": sum(x["tier"] == tier for x in headline),
                "preceded": sum(x["tier"] == tier and x["preceded"] for x in headline),
                "preceded_within_14d": sum(x["tier"] == tier and x["timely"] for x in headline),
            }
            for tier in ("dev", "test")
        },
        "rotation_counts": {
            "episodes": len(rotation),
            "preceded": sum(x["preceded"] for x in rotation),
            "preceded_within_14d": sum(x["timely"] for x in rotation),
        },
        "episodes": headline,
        "rotation_episodes": rotation,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(report, indent=2) + "\n")
    print(report["note"])
    print("2022 dev:", summarize(headline, "dev"))
    print(f"rotation stations {sorted(ROTATION_STATIONS)}: {len(rotation)} episodes (excluded)")
    print(f"wrote reports/{name} (2023 test tier is in the file only)")


if __name__ == "__main__":
    main(sys.argv[1:])
