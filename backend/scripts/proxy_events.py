"""Real "pump out of service" proxy events (ARCHITECTURE.md §5.7).

MEASUREMENT ONLY. These are weak, unlabeled proxies (a removal is not a failure). They are never used for
tuning or for choosing any parameter.

Episode: a pump whose trailing baseline median is >= 10 runs/day has 0 runs for >= 2 consecutive days while a
sibling has >= 10 runs on every episode day. Episodes overlapping 2023-08-17..20 or >= 6 h with no pump event
at the station are excluded (a data gap, not a removal).
Preceded: any WATCH or INVESTIGATE (pump CAPACITY_DROP or STATION_WIDE_CHANGE; never PUMP_NOT_RUNNING) opened
>= 1 day before the episode start and still open the day before it.
Rotation station: more than half of its episodes last exactly 2 days (duty rotation, not failure). Reported
separately and excluded from the headline counts.

Usage:
  python -m backend.scripts.proxy_events                  # the 3 demo stations, from fixtures
  WESSEX_DIR=... python -m backend.scripts.proxy_events --all-stations   # adds the 21 untouched stations
Only 2022 (dev) is printed and written. 2023 (test) is written only with FREEZE=1 (§6.5: scored once).
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
SILENCE = pd.Timedelta(hours=6)
EXCLUDED_WINDOWS = [(pd.Timestamp("2023-08-17"), pd.Timestamp("2023-08-21"))]  # 17-20 Aug 2023, end exclusive
END = "2024-01-01T00:00:00Z"
OUT = Path(__file__).resolve().parents[2] / "reports"


def silences(ts: pd.Series, gap: pd.Timedelta = SILENCE) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Intervals with no timestamp for >= gap (applied to the station's pump events)."""
    t = ts.sort_values().drop_duplicates().reset_index(drop=True)
    d = t.diff()
    return [(t[i - 1], t[i]) for i in d.index[d >= gap]]


def _opened_before(r_pump: pd.DataFrame, station_days: pd.DataFrame, start: pd.Timestamp):
    """Open date of a WATCH/INVESTIGATE still open the day before `start` and opened >= 1 day earlier."""
    prev = start - pd.Timedelta(days=1)
    opened = []
    row = r_pump[r_pump["day"] == prev]
    if len(row) and isinstance(row["incident_id"].iloc[0], str):
        opened.append(pd.Timestamp(row["incident_id"].iloc[0].rsplit(":", 1)[1]))
    sw = station_days[station_days["day"] <= prev].sort_values("day")
    if len(sw) and sw["station_wide_status"].iloc[-1] != "NORMAL":
        run_start = sw[sw["station_wide_status"] == "NORMAL"]["day"].max()
        opened.append(sw["day"].min() if pd.isna(run_start) else run_start + pd.Timedelta(days=1))
    opened = [o for o in opened if o <= prev]
    return min(opened) if opened else None


def episodes(r: pd.DataFrame, silent: list | None = None) -> list[dict]:
    """Episodes in a detect.run output (needs pump_id, day, runs, base_runs_median, incident_id,
    station_wide_status). `silent` = station silence intervals to exclude."""
    blocked = EXCLUDED_WINDOWS + list(silent or [])
    sib = r.groupby("day")["runs"].transform(
        "max"
    )  # the pump itself has 0 runs, so this is the busiest sibling
    cand = (r["base_runs_median"] >= BUSY) & (r["runs"] == 0) & (sib >= BUSY)
    station_days = r.drop_duplicates("day")[["day", "station_wide_status"]]
    out = []
    for pump, g in r.assign(cand=cand).sort_values("day").groupby("pump_id"):
        g = g.reset_index(drop=True)
        block = (g["cand"] != g["cand"].shift()).cumsum()
        for _, b in g[g["cand"]].groupby(block[g["cand"]]):
            if len(b) < MIN_DAYS:
                continue
            start, end = b["day"].min(), b["day"].max()
            stop = end + pd.Timedelta(days=1)
            if any(a < stop and z > start for a, z in blocked):
                continue
            first = _opened_before(g, station_days, start)
            out.append(
                {
                    "station": str(r["station_id"].iloc[0]),
                    "pump": pump,
                    "start": start.date().isoformat(),
                    "end": end.date().isoformat(),
                    "days": len(b),
                    "tier": "dev"
                    if start.year == 2022
                    else "test"
                    if start.year == 2023
                    else str(start.year),
                    "preceded": first is not None,
                    "first_alert_day": first.date().isoformat() if first is not None else None,
                    "lead_days": int((start - first).days) if first is not None else None,
                }
            )
    return out


def is_rotation(eps: list[dict]) -> bool:
    """More than half of the station's episodes last exactly 2 days."""
    return bool(eps) and sum(e["days"] == 2 for e in eps) > len(eps) / 2


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
        # shortcut: no level stream in all-station mode, so ordinary >10 min gaps between pump events would
        # count as silence; use 6 h of pump-event silence instead. Upgrade: load level for all 24 stations.
        first, last = t["day"].min(), t["day"].max() + pd.Timedelta(days=1)
        off = features.offline_hours_by_day(events["ts"], first, last, SILENCE)
        t["offline_hours"] = t["day"].map(off).fillna(0.0)
        t["quality"] = t.apply(features.day_quality, axis=1)
    # pump-event silence, not level: a station whose pumps log nothing for 6 h is a data gap (matches Dhruv's 16)
    return episodes(detect.run(t, params.load()), silences(events["ts"]))


def counts(eps: list[dict], tiers: tuple[str, ...]) -> dict:
    return {
        t: {
            "episodes": sum(e["tier"] == t for e in eps),
            "preceded": sum(e["tier"] == t and e["preceded"] for e in eps),
        }
        for t in tiers
    }


def group(eps_by_station: dict[str, list[dict]], tiers) -> dict:
    rot = sorted(st for st, e in eps_by_station.items() if is_rotation(e))
    head = [ep for st, eps in eps_by_station.items() if st not in rot for ep in eps]
    rest = [ep for st in rot for ep in eps_by_station[st]]
    return {
        "stations": sorted(eps_by_station),
        "rotation_stations": rot,
        "counts": counts(head, tiers),
        "rotation_counts": counts(rest, tiers),
        "episodes": [e for e in head if e["tier"] in tiers],
        "rotation_episodes": [e for e in rest if e["tier"] in tiers],
    }


def summary(name: str, g: dict) -> str:
    c, rc = g["counts"]["dev"], g["rotation_counts"]["dev"]
    return (
        f"{name}: 2022 dev {c['episodes']} episodes, {c['preceded']} preceded | rotation stations "
        f"{g['rotation_stations'] or 'none'}: {rc['episodes']} episodes, {rc['preceded']} preceded (excluded)"
    )


def main(argv: list[str]) -> None:
    tiers = ("dev", "test") if os.environ.get("FREEZE") == "1" else ("dev",)
    demo = {}
    for st in data.STATIONS:
        s = data.load(st)
        demo[st] = run_station(st, s.events, s.level, s.rain)
    report = {
        "note": "Measurement only: weak proxies for 'pump out of service', never used for tuning (§5.7).",
        "tiers_written": list(tiers),
        "demo_stations": group(demo, tiers),
    }
    lines = [summary("3 demo stations", report["demo_stations"])]
    name = "proxy_events.json"
    if "--all-stations" in argv:
        raw = pd.read_csv(Path(os.environ["WESSEX_DIR"]).expanduser() / "sps-run-stop-data.csv", dtype=str)
        raw.columns = ["signal_id", "ts", "value"]
        raw["station"] = raw["signal_id"].str.split("_").str[0]
        other = {}
        for st, g in raw[~raw["station"].isin(data.STATIONS)].groupby("station"):
            other[st] = run_station(st, quality.parse_events(g[["signal_id", "ts", "value"]], {}))
        report["untouched_stations"] = group(other, tiers)
        report["untouched_stations"]["note"] = (
            "No level data in this mode: silence = 6 h without pump events."
        )
        lines.append(summary(f"{len(other)} untouched stations", report["untouched_stations"]))
        name = "proxy_events_all_stations.json"
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(report, indent=2) + "\n")
    print(report["note"])
    print("\n".join(lines))
    print(f"wrote reports/{name} (tiers: {', '.join(tiers)})")


if __name__ == "__main__":
    main(sys.argv[1:])
