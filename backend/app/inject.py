"""Fault injection on real event streams (ARCHITECTURE.md §5.2, §5.6).

Every transform takes and returns a StationData copy plus a `truth` dict. Truth goes only to the evaluator
and replay_case (§5.8); features.py and detect.py never see it. Level and rain stay real unless the
transform says otherwise.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from . import quality
from .data import StationData
from .scenarios import loss_at

CAP_S = quality.RUN_MAX_S


def _runs(sd: StationData) -> pd.DataFrame:
    c: dict = {}
    return quality.cycles(quality.pair_runs(sd.events, c), c)


def _to_events(runs: pd.DataFrame, sd: StationData) -> pd.DataFrame:
    sig = sd.events.drop_duplicates("pump_id").set_index("pump_id")["signal_id"]
    on = pd.DataFrame({"pump_id": runs["pump_id"], "ts": runs["start"], "state": 1})
    off = pd.DataFrame({"pump_id": runs["pump_id"], "ts": runs["end"], "state": 0})
    ev = pd.concat([on, off], ignore_index=True)
    ev["ts"] = ev["ts"].dt.round("s")
    ev["signal_id"] = ev["pump_id"].map(sig)
    return ev.sort_values(["pump_id", "ts", "state"]).reset_index(drop=True)[
        ["signal_id", "pump_id", "ts", "state"]
    ]


def _retime(r: pd.DataFrame, new_run: pd.Series) -> pd.DataFrame:
    """Replace run lengths and shift every later station event by the added seconds."""
    r = r.sort_values("start").reset_index(drop=True)
    delta = (new_run.reindex(r.index).fillna(r["run_s"]) - r["run_s"]).to_numpy()
    before = np.cumsum(delta) - delta
    r["start"] = r["start"] + pd.to_timedelta(before, unit="s")
    r["end"] = r["end"] + pd.to_timedelta(before + delta, unit="s")
    r["run_s"] = (r["end"] - r["start"]).dt.total_seconds()
    r.attrs["shift_s"] = float(delta.sum())
    return r


def _loss_run(r: pd.DataFrame, mask: pd.Series, loss: np.ndarray) -> pd.Series:
    """run' = min(3600 / (CI' - I), 3600), exactly 3600 when CI' <= I (§5.2 cap)."""
    return _run_for_ci(r, mask, lambda ci: ci * (1 - loss))


def _run_for_ci(r: pd.DataFrame, mask: pd.Series, new_ci) -> pd.Series:
    """Recompute run time for a new pump capacity CI' at the cycle's own inflow I = 3600/fill.
    Cycles without a usable fill (overlap, gaps) scale run by CI/CI', so every cycle feels the change."""
    fill = r.loc[mask, "fill_s"]
    run = r.loc[mask, "run_s"].clip(upper=CAP_S)
    ok = fill.between(quality.FILL_MIN_S, quality.FILL_MAX_S)
    inflow = (3600 / fill).where(ok, 0.0)
    ci = 3600 / run + inflow
    ci_new = new_ci(ci)
    head = ci_new - inflow
    new = np.where(head > 0, np.minimum(3600 / head.where(head > 0, 1), CAP_S), CAP_S)
    scaled = np.minimum(run * ci / ci_new, CAP_S)
    return pd.Series(np.where(ok, new, scaled), index=run.index)


def sibling_of(sd: StationData, pump: str) -> str:
    counts = sd.events[(sd.events.state == 1) & (sd.events.pump_id != pump)]["pump_id"].value_counts()
    return str(counts.index[0])


def capacity_loss(sd, pump, onset, failure, loss_24h, shape="linear"):
    r = _runs(sd).sort_values("start").reset_index(drop=True)
    onset, failure = pd.Timestamp(onset), pd.Timestamp(failure)
    m = (r["pump_id"] == pump) & (r["start"] >= onset) & (r["start"] < failure)
    loss = loss_at(pd.DatetimeIndex(r.loc[m, "start"]), onset, failure, loss_24h, shape)
    r = _retime(r, _loss_run(r, m, loss))
    sib = sibling_of(sd, pump)
    # shortcut: after the trip the sibling takes the failed pump's cycles with their real timing;
    # upgrade to recompute run with the sibling's own CI if lead-time bins need it.
    after = (r["pump_id"] == pump) & (r["start"] >= failure + pd.Timedelta(seconds=r.attrs["shift_s"]))
    r.loc[after, "pump_id"] = sib
    truth = {
        "transform": "capacity_loss",
        "pump": pump,
        "onset": onset,
        "failure": failure,
        "loss_24h": loss_24h,
        "shape": shape,
        "ramp_days": (failure - onset).total_seconds() / 86400 - 1,
        "clock_shift_h": r.attrs["shift_s"] / 3600,
        "sibling": sib,
    }
    return replace(sd, events=_to_events(r, sd)), truth


def transient(sd, pump, day, loss):
    day = pd.Timestamp(day).floor("D")
    r = _runs(sd).sort_values("start").reset_index(drop=True)
    m = (r["pump_id"] == pump) & (r["start"] >= day) & (r["start"] < day + pd.Timedelta(days=1))
    new = _loss_run(r, m, np.full(int(m.sum()), loss))
    # one day of OUTPUT time: capped runs push later cycles back, so stop once the shifted start leaves the
    # day; otherwise a 1-day dip at the run cap stretches over ~3 days and becomes a sustained loss
    delta = (new.reindex(r.index).fillna(r["run_s"]) - r["run_s"]).to_numpy()
    shifted = r["start"] + pd.to_timedelta(np.cumsum(delta) - delta, unit="s")
    new = new[(shifted.reindex(new.index) < day + pd.Timedelta(days=1)).to_numpy()]
    r = _retime(r, new)
    return replace(sd, events=_to_events(r, sd)), {
        "transform": "transient",
        "pump": pump,
        "day": day,
        "loss": loss,
    }


def station_shift(sd, onset, factor):
    onset = pd.Timestamp(onset)
    r = _runs(sd).sort_values("start").reset_index(drop=True)
    m = r["start"] >= onset
    r = _retime(r, _loss_run(r, m, np.full(int(m.sum()), 1 - factor)))
    return replace(sd, events=_to_events(r, sd)), {
        "transform": "station_shift",
        "onset": onset,
        "factor": factor,
    }


def duty_swap(sd, pump, onset, days, share, rng):
    onset = pd.Timestamp(onset)
    r = _runs(sd).sort_values("start").reset_index(drop=True)
    m = (r["start"] >= onset) & (r["start"] < onset + pd.Timedelta(days=days))
    sib = sibling_of(sd, pump)
    pick = rng.random(int(m.sum())) < share
    target = pd.Series(np.where(pick, pump, sib), index=r.index[m])
    # a relabelled cycle runs at the TARGET pump's own capacity, not the original pump's
    ci_pump = r[r["valid"] & (r["start"] < onset)].groupby("pump_id")["ci"].median()
    moved = m & (r["pump_id"] != target.reindex(r.index))
    ci_t = target[moved[m].to_numpy()].map(ci_pump)
    if moved.any():
        r = _retime(r, _run_for_ci(r, moved, lambda ci: ci_t.reindex(ci.index)))
    r.loc[m, "pump_id"] = target.to_numpy()
    truth = {"transform": "duty_swap", "pump": pump, "onset": onset, "days": days, "share": share}
    return replace(sd, events=_to_events(r, sd)), truth


def outage(sd, start, hours):
    start = pd.Timestamp(start)
    end = start + pd.Timedelta(hours=hours)
    ev = sd.events[~sd.events.ts.between(start, end, inclusive="left")]
    lv = sd.level[~sd.level.ts.between(start, end, inclusive="left")]
    return replace(sd, events=ev, level=lv), {"transform": "outage", "start": start, "end": end}


SENSOR_KINDS = ["flatline", "dropout", "negative_spikes", "duplicate_rows", "repeated_starts"]


def sensor_fault(sd, kind, start, rng):
    start = pd.Timestamp(start)
    ev, lv = sd.events.copy(), sd.level.copy()
    if kind == "flatline":
        w = lv.ts.between(start, start + pd.Timedelta(hours=12), inclusive="left")
        lv.loc[w, "value"] = float(lv.loc[w, "value"].iloc[0])
    elif kind == "dropout":
        lv = lv[~lv.ts.between(start, start + pd.Timedelta(hours=6), inclusive="left")]
    elif kind == "negative_spikes":  # 20 min/day of negative readings for 3 days (>= 15 min/day)
        for k in range(3):
            w = lv.ts.between(
                start + pd.Timedelta(days=k), start + pd.Timedelta(days=k, minutes=20), inclusive="left"
            )
            lv.loc[w, ["value", "in_range"]] = [-5.0, False]
    elif kind == "duplicate_rows":
        ev = pd.concat([ev, ev.sample(frac=0.05, random_state=int(rng.integers(1 << 31)))]).sort_values(
            ["pump_id", "ts"]
        )
    elif kind == "repeated_starts":
        starts = ev[ev.state == 1].sample(frac=0.05, random_state=int(rng.integers(1 << 31))).copy()
        starts["ts"] = starts["ts"] + pd.Timedelta(seconds=1)
        ev = pd.concat([ev, starts]).sort_values(["pump_id", "ts", "state"])
    else:
        raise ValueError(kind)
    return replace(sd, events=ev.reset_index(drop=True), level=lv.reset_index(drop=True)), {
        "transform": "sensor_fault",
        "kind": kind,
        "start": start,
    }
