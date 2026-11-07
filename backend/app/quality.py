"""Data-quality rules (ARCHITECTURE.md §3.5) and per-pump run pairing.

Every rule counts what it touches; nothing is dropped silently. Pairing is strictly within a pump.
Binary pump state is never forward-filled.
"""

from __future__ import annotations

import pandas as pd

RUN_MIN_S, RUN_MAX_S = 5, 3600
FILL_MIN_S, FILL_MAX_S = 10, 6 * 3600
LEVEL_GAP = pd.Timedelta(minutes=15)
LEVEL_FLATLINE = pd.Timedelta(hours=6)
LEVEL_PCT_MAX = 105.0


def pump_id_of(signal_id: str) -> str:
    """'44371_PFFPump2_WASTE_B24899' -> 'P2'."""
    part = signal_id.split("_")[1]
    return "P" + part.removeprefix("PFFPump")


def parse_events(raw: pd.DataFrame, counts: dict) -> pd.DataFrame:
    """Raw run/stop rows (signal_id, ts, value as str) -> typed events with pump_id; counts drops."""
    df = raw.copy()
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", format="%Y-%m-%d %H:%M:%S")
    bad = df["ts"].isna()
    counts["BAD_TIMESTAMP"] = counts.get("BAD_TIMESTAMP", 0) + int(bad.sum())
    df = df[~bad]
    dup = df.duplicated(["signal_id", "ts", "value"])
    counts["DUPLICATE_ROW"] = counts.get("DUPLICATE_ROW", 0) + int(dup.sum())
    df = df[~dup]
    df["state"] = pd.to_numeric(df["value"], errors="coerce").round().astype("Int64")
    badv = ~df["state"].isin([0, 1])
    counts["BAD_VALUE"] = counts.get("BAD_VALUE", 0) + int(badv.sum())
    df = df[~badv]
    df["pump_id"] = df["signal_id"].map(pump_id_of)
    return df.sort_values(["pump_id", "ts", "state"]).reset_index(drop=True)[
        ["signal_id", "pump_id", "ts", "state"]
    ]


def pair_runs(events: pd.DataFrame, counts: dict) -> pd.DataFrame:
    """Pair start->stop within each pump. Keeps the first of repeated starts / stops.

    Returns runs: pump_id, start, end, run_s (end may be NaT for OPEN_RUN, which is excluded).
    """
    out = []
    for pump, g in events.groupby("pump_id", sort=True):
        s = g["state"].to_numpy()
        t = g["ts"].to_numpy()
        prev = pd.Series(s).shift().to_numpy()
        repeat = s == prev  # same state as the previous event of this pump
        counts["REPEATED_START"] = counts.get("REPEATED_START", 0) + int((repeat & (s == 1)).sum())
        counts["REPEATED_STOP"] = counts.get("REPEATED_STOP", 0) + int((repeat & (s == 0)).sum())
        keep = ~repeat
        s, t = s[keep], t[keep]
        # drop a leading stop (no start before it)
        if len(s) and s[0] == 0:
            counts["LEADING_STOP"] = counts.get("LEADING_STOP", 0) + 1
            s, t = s[1:], t[1:]
        starts = t[0::2]
        stops = t[1::2]
        if len(starts) > len(stops):
            counts["OPEN_RUN"] = counts.get("OPEN_RUN", 0) + 1
            starts = starts[: len(stops)]
        out.append(pd.DataFrame({"pump_id": pump, "start": starts, "end": stops}))
    runs = pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["pump_id", "start", "end"])
    runs["run_s"] = (runs["end"] - runs["start"]).dt.total_seconds()
    return runs


def cycles(runs: pd.DataFrame, counts: dict) -> pd.DataFrame:
    """Add fill_s, flags and the capacity index CI = 3600/run + 3600/fill (§4.1).

    fill_i = start_i - (latest end among runs of ANY pump that started before run i).
    """
    r = runs.sort_values(["start", "pump_id"]).reset_index(drop=True)
    prev_end = r["end"].shift().cummax()
    r["overlap"] = r["start"] < prev_end
    r["fill_s"] = (r["start"] - prev_end).dt.total_seconds()
    r["run_oor"] = ~r["run_s"].between(RUN_MIN_S, RUN_MAX_S)
    r["fill_oor"] = ~r["fill_s"].between(FILL_MIN_S, FILL_MAX_S)  # NaN (first run) -> out of range
    r["valid"] = ~(r["overlap"] | r["run_oor"] | r["fill_oor"])
    r["ci"] = (3600 / r["run_s"] + 3600 / r["fill_s"]).where(r["valid"])
    counts["RUN_OUT_OF_RANGE"] = counts.get("RUN_OUT_OF_RANGE", 0) + int(r["run_oor"].sum())
    counts["FILL_OUT_OF_RANGE"] = counts.get("FILL_OUT_OF_RANGE", 0) + int(r["fill_oor"].sum())
    counts["OVERLAP"] = counts.get("OVERLAP", 0) + int(r["overlap"].sum())
    return r


def parse_level(raw: pd.DataFrame, counts: dict) -> pd.DataFrame:
    """Typed level samples with an in_range flag. Out-of-range samples are kept but flagged."""
    df = raw.copy()
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", format="%Y-%m-%d %H:%M:%S")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    bad = df["ts"].isna() | df["value"].isna()
    counts["LEVEL_BAD_ROW"] = counts.get("LEVEL_BAD_ROW", 0) + int(bad.sum())
    df = df[~bad]
    dup = df.duplicated(["signal_id", "ts"])
    counts["LEVEL_DUPLICATE_ROW"] = counts.get("LEVEL_DUPLICATE_ROW", 0) + int(dup.sum())
    df = df[~dup].sort_values("ts").reset_index(drop=True)
    pct = df["units"].astype(str).str.strip() == "%"
    oor = (df["value"] < 0) | (pct & (df["value"] > LEVEL_PCT_MAX))
    df["in_range"] = ~oor
    counts["LEVEL_OUT_OF_RANGE"] = counts.get("LEVEL_OUT_OF_RANGE", 0) + int(oor.sum())
    return df[["signal_id", "ts", "value", "units", "in_range"]]


def level_day_flags(level: pd.DataFrame, runs: pd.DataFrame) -> pd.DataFrame:
    """Per UTC day: LEVEL_OUT_OF_RANGE (>1% of day's samples), LEVEL_FLATLINE (unchanged >=6 h while
    pumps cycle), LEVEL_GAP (any gap >=15 min). Returns DataFrame day -> list of flags, gap_hours."""
    if level.empty:
        return pd.DataFrame(columns=["day", "level_flags", "level_gap_hours"])
    lv = level.sort_values("ts")
    day = lv["ts"].dt.floor("D")
    oor_share = (~lv["in_range"]).groupby(day).mean()

    # gaps: allocate gap time to the day the gap started (good enough at day resolution)
    gap = lv["ts"].diff().shift(-1)
    gap_hours = gap.where(gap >= LEVEL_GAP).dt.total_seconds().div(3600).groupby(day).sum()

    # flatline: runs of identical values lasting >= 6 h, during which some pump ran
    block = (lv["value"].diff() != 0).cumsum()
    span = lv.groupby(block)["ts"].agg(["min", "max"])
    long = span[(span["max"] - span["min"]) >= LEVEL_FLATLINE]
    flat_days: set = set()
    for lo, hi in long.itertuples(index=False):
        if ((runs["start"] >= lo) & (runs["start"] <= hi)).any():
            flat_days.update(pd.date_range(lo.floor("D"), hi.floor("D"), freq="D"))

    days = sorted(set(oor_share.index) | flat_days)
    rows = []
    for d in days:
        f = []
        if oor_share.get(d, 0) > 0.01:
            f.append("LEVEL_OUT_OF_RANGE")
        if d in flat_days:
            f.append("LEVEL_FLATLINE")
        if gap_hours.get(d, 0) > 0:
            f.append("LEVEL_GAP")
        rows.append({"day": d, "level_flags": f, "level_gap_hours": float(gap_hours.get(d, 0.0))})
    return pd.DataFrame(rows)
