"""Capacity-index detector (ARCHITECTURE.md §4.4-4.8).

detect.run      daily, complete-day logic: baseline, sibling inhibition, CUSUM, status, incidents.
detect.realtime minute-resolution safety/quality findings up to as_of: SOURCE_SILENT, HIGH_LEVEL, SENSOR_FAULT.
Rain is never used to suppress anything. HIGH_LEVEL has no inhibition path.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .features import to_naive_utc
from .params import Params

MAD_SCALE = 1.4826
STANDBY_RUNS_PER_DAY = 5
NOT_RUNNING_MIN_RUNS = 10


# --------------------------------------------------------------------------- daily


def _baseline(day_idx: np.ndarray, logci: np.ndarray, ok: np.ndarray, runs: np.ndarray, p: Params):
    """Trailing per-pump baseline over days [d-G-W, d-G-1], SUFFICIENT days only."""
    n = len(day_idx)
    med = np.full(n, np.nan)
    mad = np.full(n, np.nan)
    nbase = np.zeros(n, dtype=int)
    runs_med = np.full(n, np.nan)
    for i in range(n):
        lo, hi = day_idx[i] - p.G - p.W, day_idx[i] - p.G - 1
        win = (day_idx >= lo) & (day_idx <= hi)
        sel = win & ok
        nbase[i] = int(sel.sum())
        if win.any():
            runs_med[i] = float(np.median(runs[win]))
        if nbase[i] >= p.min_baseline_days:
            x = logci[sel]
            med[i] = float(np.median(x))
            mad[i] = float(np.median(np.abs(x - med[i])))
    return med, mad, nbase, runs_med


def run(daily: pd.DataFrame, params: Params, scope: str = "REAL") -> pd.DataFrame:
    """Add base_median, base_mad, z, common, u, cusum, station_cusum, status, incident_id,
    transition_reason (+ capacity_change_pct, baseline_days, standby, pump_not_running,
    station_wide_change) to the daily table."""
    p = params
    d = daily.copy().sort_values(["pump_id", "day"]).reset_index(drop=True)
    if d.empty:
        return d
    d["sufficient"] = (d["quality"] == "SUFFICIENT") if p.quality_gate else d["ci"].notna()
    d["sufficient"] &= d["ci"].notna()
    day0 = d["day"].min()
    d["day_idx"] = (d["day"] - day0).dt.days
    d["logci"] = np.log(d["ci"])

    parts = []
    for _pump, g in d.groupby("pump_id", sort=True):
        g = g.copy()
        med, mad, nbase, runs_med = _baseline(
            g["day_idx"].to_numpy(),
            g["logci"].to_numpy(),
            g["sufficient"].to_numpy(),
            g["runs"].to_numpy(),
            p,
        )
        g["base_median"], g["base_mad"], g["baseline_days"], g["base_runs_median"] = med, mad, nbase, runs_med
        parts.append(g)
    d = pd.concat(parts, ignore_index=True)

    scale = np.maximum(MAD_SCALE * d["base_mad"], 0.01)
    d["z"] = ((d["logci"] - d["base_median"]) / scale).clip(-10, 10)
    d.loc[~d["sufficient"], "z"] = np.nan
    d["capacity_change_pct"] = 100 * (np.exp(d["logci"] - d["base_median"]) - 1)
    d["standby"] = d["base_runs_median"] < STANDBY_RUNS_PER_DAY

    # sibling inhibition (§4.5, decision D2/D3): compare the capacity CHANGE (log CI minus own baseline) with
    # the other sufficient pumps' changes, subtract only a shared drop, then scale by this pump's own spread.
    d["dev"] = (d["logci"] - d["base_median"]).where(d["z"].notna())
    ds = d.dropna(subset=["dev"])
    others = []
    for r in d[["pump_id", "day"]].itertuples(index=False):
        o = ds[(ds["day"] == r.day) & (ds["pump_id"] != r.pump_id)]["dev"]
        others.append(float(o.median()) if len(o) else np.nan)
    oth = np.array(others, dtype=float)
    d["sibling_available"] = ~np.isnan(oth)
    oth = np.nan_to_num(oth, nan=0.0)
    if p.sibling_mode == "shared_drop":  # only explain a drop the siblings share; never manufacture one
        oth = np.minimum(oth, 0.0)
    if not p.inhibition:
        oth = np.zeros_like(oth)
    d["common"] = oth / scale  # in this pump's z units, for the trace
    d["u"] = ((d["dev"] - oth) / scale).clip(-10, 10)
    zs = d.dropna(subset=["z"])
    # station-wide signal c_d = max z over sufficient pumps (>= 2), negative only if every pump drops
    zc = zs.groupby("day")["z"]
    common = zc.max().where(zc.count() >= 2)

    # per-pump CUSUM + status (§4.6) and incidents (§4.11)
    parts = []
    for pump, g in d.groupby("pump_id", sort=True):
        parts.append(_pump_states(g.sort_values("day").copy(), pump, p, scope))
    d = pd.concat(parts, ignore_index=True)

    # station-wide change (§4.7): same CUSUM on -c_d, WATCH at most
    st = common.dropna().sort_index()
    s, on, scus, son = 0.0, False, {}, {}
    for day, c in st.items():
        s = min(p.S_max, max(0.0, s + float(np.clip(-c, -p.U, p.U)) - p.k))
        on = s >= p.h_w or (on and s >= 1.0)  # opens at h_w, closes below 1.0 (same hysteresis as WATCH)
        scus[day], son[day] = s, on
    days = pd.Series(sorted(d["day"].unique()))
    scs = pd.Series(scus, dtype=float).reindex(days).ffill().fillna(0.0)  # held on days without siblings
    sow = pd.Series(son, dtype=object).reindex(days).ffill().fillna(False).astype(bool)
    d["station_cusum"] = d["day"].map(scs)
    d["station_wide_change"] = d["day"].map(sow).astype(bool)

    # PUMP_NOT_RUNNING (§4.8): baseline runs/day median >= 10, today 0, a sibling >= 10 today
    sib_max = d.groupby("day")["runs"].transform("max")
    d["pump_not_running"] = (
        (d["base_runs_median"] >= NOT_RUNNING_MIN_RUNS) & (d["runs"] == 0) & (sib_max >= NOT_RUNNING_MIN_RUNS)
    )

    keep = [c for c in d.columns if c not in ("day_idx", "logci", "sufficient", "dev")]
    return d[keep].sort_values(["day", "pump_id"]).reset_index(drop=True)


def _pump_states(g: pd.DataFrame, pump: str, p: Params, scope: str) -> pd.DataFrame:
    station = str(g["station_id"].iloc[0])
    S, status = 0.0, "INSUFFICIENT_EVIDENCE"
    recent: list[float] = []  # u on the last SUFFICIENT days
    open_id: str | None = None
    closed_on: pd.Timestamp | None = None
    last_id: str | None = None
    out_s, out_status, out_id, out_reason = [], [], [], []
    for r in g.itertuples(index=False):
        prev = status
        reason = None
        if r.baseline_days < p.min_baseline_days:
            new = "INSUFFICIENT_EVIDENCE"
        elif not (isinstance(r.u, float) and not math.isnan(r.u)):
            # PARTIAL / INSUFFICIENT / SOURCE_OFFLINE day: hold S and status
            new = prev if prev != "INSUFFICIENT_EVIDENCE" else "NORMAL"
        else:
            if p.persistence:
                S = min(p.S_max, max(0.0, S + float(np.clip(-r.u, -p.U, p.U)) - p.k))
                recent = (recent + [r.u])[-3:]
                persist = sum(x < -p.k for x in recent) >= 2
                if S >= p.h_i and persist:
                    new = "INVESTIGATE"
                elif prev == "INVESTIGATE":
                    new = "INVESTIGATE" if S >= p.h_w else "WATCH"
                elif S >= p.h_w or prev == "WATCH" and S >= 1.0:
                    new = "WATCH"
                else:
                    new = "NORMAL"
            else:  # ablation: single-day threshold on u
                new = "INVESTIGATE" if r.u < -5 else "WATCH" if r.u < -3 else "NORMAL"
        if new != prev:
            reason = _reason(prev, new, S, r, p)
        # incident tracking: one CAPACITY_DROP incident while WATCH/INVESTIGATE
        active = new in ("WATCH", "INVESTIGATE")
        if active and open_id is None:
            if last_id and closed_on is not None and (r.day - closed_on).days <= p.reopen_days:
                open_id = last_id
            else:
                open_id = f"{scope}:{station}:{pump}:CAPACITY_DROP:{r.day.date().isoformat()}"
        elif not active and open_id is not None:
            last_id, closed_on, open_id = open_id, r.day, None
        status = new
        out_s.append(S)
        out_status.append(new)
        out_id.append(open_id)
        out_reason.append(reason)
    g["cusum"], g["status"], g["incident_id"], g["transition_reason"] = out_s, out_status, out_id, out_reason
    return g


def _reason(prev: str, new: str, S: float, r, p: Params) -> str:
    if new == "INSUFFICIENT_EVIDENCE":
        return f"warming up: {r.baseline_days} baseline days < {p.min_baseline_days}"
    if new == "INVESTIGATE":
        return f"CUSUM {S:.1f} >= {p.h_i} with 2 of last 3 sufficient days below -k"
    if new == "WATCH" and prev == "INVESTIGATE":
        return f"CUSUM {S:.1f} fell below {p.h_w}"
    if new == "WATCH":
        return f"CUSUM {S:.1f} >= {p.h_w}"
    if prev == "INSUFFICIENT_EVIDENCE":
        return "baseline ready"
    return f"CUSUM {S:.1f} recovered"


# --------------------------------------------------------------------------- realtime


def realtime(events: pd.DataFrame, level: pd.DataFrame, as_of, params: Params) -> list[dict]:
    """SOURCE_SILENT, HIGH_LEVEL, SENSOR_FAULT from data strictly before as_of (§4.8)."""
    end = to_naive_utc(as_of)
    ev = events[(events["ts"] < end) & (events["ts"] >= end - pd.Timedelta(days=60))]
    lv = level[(level["ts"] < end) & (level["ts"] >= end - pd.Timedelta(days=60))]
    out: list[dict] = []

    # --- SOURCE_SILENT: level heartbeat (5 missed samples) or pump-event heartbeat (T)
    reasons = []
    if len(lv) >= 2:
        cadence = lv["ts"].diff().dt.total_seconds().median()
        since = (end - lv["ts"].max()).total_seconds()
        if since >= 5 * cadence:
            reasons.append(f"level: no sample for {since / 60:.0f} min (cadence {cadence:.0f} s)")
    if len(ev) >= 2:
        starts = ev[ev["state"] == 1].sort_values("ts")["ts"]
        stops = ev[ev["state"] == 0].sort_values("ts")["ts"]
        fills = _fills(starts, stops)
        T = max(20 * 60, 3 * float(np.percentile(fills, 99))) if len(fills) else 20 * 60
        since = (end - ev["ts"].max()).total_seconds()
        if since >= T:
            reasons.append(f"pump events: none for {since / 60:.0f} min (T = {T / 60:.0f} min)")
    elif len(ev) == 0:
        reasons.append("pump events: none in 60 days")
    if reasons:
        last = max(
            [
                x
                for x in (ev["ts"].max() if len(ev) else None, lv["ts"].max() if len(lv) else None)
                if x is not None
            ],
            default=None,
        )
        out.append({"type": "SOURCE_SILENT", "status": "SOURCE_OFFLINE", "since": last, "reasons": reasons})

    # --- HIGH_LEVEL: >= trailing 60-day P99.9 for 5 consecutive minutes in the last 24 h. Never inhibited.
    good = lv[lv["in_range"]] if "in_range" in lv else lv
    if len(good) > 100:
        thr = float(np.percentile(good["value"], 99.9))
        last24 = good[good["ts"] >= end - pd.Timedelta(hours=24)].sort_values("ts")
        if len(last24):
            above = last24["value"] >= thr
            block = (above != above.shift()).cumsum()
            for _, b in last24[above].groupby(block[above]):
                if b["ts"].max() - b["ts"].min() >= pd.Timedelta(minutes=4):  # 5 consecutive 1-min samples
                    out.append(
                        {
                            "type": "HIGH_LEVEL",
                            "status": "INVESTIGATE",
                            "threshold": thr,
                            "at": b["ts"].min(),
                            "peak": float(b["value"].max()),
                            "note": "SCADA-equivalent; real setpoints unknown",
                        }
                    )
                    break

    # --- SENSOR_FAULT: level flags over the last 24 h
    day = lv[lv["ts"] >= end - pd.Timedelta(hours=24)]
    flags = []
    if len(day):
        if (~day["in_range"]).mean() > 0.01:
            flags.append("LEVEL_OUT_OF_RANGE")
        blk = (day["value"].diff() != 0).cumsum()
        span = day.groupby(blk)["ts"].agg(["min", "max"])
        long = span[(span["max"] - span["min"]) >= pd.Timedelta(hours=6)]
        for lo, hi in long.itertuples(index=False):
            if ((ev["ts"] >= lo) & (ev["ts"] <= hi) & (ev["state"] == 1)).any():
                flags.append("LEVEL_FLATLINE")
                break
    if flags:
        out.append(
            {
                "type": "SENSOR_FAULT",
                "status": "WATCH",
                "flags": flags,
                "effect": "HIGH_LEVEL check is UNKNOWN while the level sensor is faulty"
                if "LEVEL_FLATLINE" in flags
                else "station quality capped at PARTIAL",
            }
        )
    return out


def _fills(starts: pd.Series, stops: pd.Series) -> np.ndarray:
    """Seconds from the latest station stop before each start to that start."""
    if not len(starts) or not len(stops):
        return np.array([])
    s = starts.to_numpy()
    e = np.sort(stops.to_numpy())
    idx = np.searchsorted(e, s) - 1
    ok = idx >= 0
    f = (s[ok] - e[idx[ok]]).astype("timedelta64[s]").astype(float)
    return f[(f >= 10) & (f <= 6 * 3600)]
