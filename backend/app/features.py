"""Daily per-pump feature table (ARCHITECTURE.md §4.2, §4.9).

One row per pump per UTC day, for complete days strictly before end_utc. Only data < end_utc is read.
"""

from __future__ import annotations

import pandas as pd

from . import params, quality

SILENT_SAMPLES = 10  # §4.8: SOURCE_SILENT after 10 missed level samples
SILENCE = pd.Timedelta(minutes=10)  # SILENT_SAMPLES x the 1-min level cadence
COLUMNS = [
    "station_id",
    "pump_id",
    "day",
    "runs",
    "valid_cycles",
    "overlap_share",
    "invalid_share",
    "offline_hours",
    "ci",
    "run_median_s",
    "fill_median_s",
    "rain_mm",
    "level_flags",
    "quality",
]


def to_naive_utc(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t


def offline_hours_by_day(
    ts: pd.Series, start: pd.Timestamp, end: pd.Timestamp, silence: pd.Timedelta = SILENCE
) -> pd.Series:
    """Hours per day during which SOURCE_SILENT held (§4.8): both streams silent, starting `silence`
    (5 level cadences) after the last telemetry timestamp of either stream, until the next one."""
    t = pd.Series(sorted(ts[(ts >= start) & (ts < end)].unique()))
    edges = pd.concat([pd.Series([start]), t, pd.Series([end])], ignore_index=True)
    lo, hi = edges[:-1].to_numpy(), edges[1:].to_numpy()
    big = (hi - lo) >= silence.to_timedelta64()
    out: dict = {}
    for a, b in zip(lo[big], hi[big]):
        a, b = pd.Timestamp(a) + silence, pd.Timestamp(b)
        d = a.floor("D")
        while d < b:
            seg = min(b, d + pd.Timedelta(days=1)) - max(a, d)
            out[d] = out.get(d, 0.0) + seg.total_seconds() / 3600
            d += pd.Timedelta(days=1)
    return pd.Series(out, dtype=float)


MIN_VALID_CYCLES = params.load().min_valid_cycles


def day_quality(r) -> str:
    if r.offline_hours > 6:
        return "SOURCE_OFFLINE"
    if r.valid_cycles < 5:
        return "INSUFFICIENT"
    if (
        r.valid_cycles >= MIN_VALID_CYCLES
        and r.overlap_share <= 0.2
        and r.offline_hours <= 1
        and r.invalid_share <= 0.2
    ):
        return "SUFFICIENT"
    return "PARTIAL"


def daily_table(events, level, rain, end_utc, station_id: str | None = None, counts: dict | None = None):
    counts = {} if counts is None else counts
    end = to_naive_utc(end_utc)
    last_day = end.floor("D")  # days < last_day are complete
    ev = events[events["ts"] < end]
    lv = level[level["ts"] < end]
    station_id = station_id or (ev["signal_id"].iloc[0].split("_")[0] if len(ev) else None)
    pumps = sorted(events["pump_id"].unique())
    if ev.empty:
        return pd.DataFrame(columns=COLUMNS)

    runs = quality.pair_runs(ev, counts)
    cyc = quality.cycles(runs, counts)
    cyc["day"] = cyc["start"].dt.floor("D")
    cyc = cyc[cyc["day"] < last_day]

    first_day = min(ev["ts"].min(), lv["ts"].min() if len(lv) else ev["ts"].min()).floor("D")
    days = pd.date_range(first_day, last_day - pd.Timedelta(days=1), freq="D")
    grid = pd.MultiIndex.from_product([pumps, days], names=["pump_id", "day"]).to_frame(index=False)

    g = cyc.groupby(["pump_id", "day"])
    agg = pd.DataFrame(
        {
            "runs": g.size(),
            "valid_cycles": g["valid"].sum(),
            "overlap_share": g["overlap"].mean(),
            "invalid_share": 1 - g["valid"].mean(),
            "ci": g["ci"].median(),
            "run_median_s": g["run_s"].median(),
            "fill_median_s": cyc[cyc["valid"]].groupby(["pump_id", "day"])["fill_s"].median(),
        }
    ).reset_index()
    t = grid.merge(agg, on=["pump_id", "day"], how="left")
    t[["runs", "valid_cycles"]] = t[["runs", "valid_cycles"]].fillna(0).astype(int)
    t[["overlap_share", "invalid_share"]] = t[["overlap_share", "invalid_share"]].fillna(0.0)

    cadence = lv["ts"].diff().median() if len(lv) >= 2 else pd.Timedelta(minutes=1)
    off = offline_hours_by_day(pd.concat([ev["ts"], lv["ts"]]), first_day, last_day, SILENT_SAMPLES * cadence)
    t["offline_hours"] = t["day"].map(off).fillna(0.0)

    rn = rain[rain["ts_hour"] < last_day].assign(day=lambda x: x["ts_hour"].dt.floor("D"))
    rg = rn.groupby("day")["mm"]
    rain_day = rg.sum(min_count=1).where(rg.count() >= 20)
    t["rain_mm"] = t["day"].map(rain_day)

    flags = quality.level_day_flags(lv[lv["ts"] < last_day], runs)
    fmap = dict(zip(flags["day"], flags["level_flags"])) if len(flags) else {}
    t["level_flags"] = t["day"].map(lambda d: fmap.get(d, []))

    t["quality"] = t.apply(day_quality, axis=1)
    t["station_id"] = station_id
    return t[COLUMNS].sort_values(["day", "pump_id"]).reset_index(drop=True)
