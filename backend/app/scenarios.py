"""Locked Indiana scenarios: load, rain analog (§5.3), inflow from the analog's real response (§5.4).

Scenario truth (mechanism, failure time) is read here for the simulator and evaluator only; it is never
attached to StationData or fed to the detector.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, quality

ROOT = Path(__file__).resolve().parents[2]
SCEN = ROOT / "fixtures" / "scenarios"
IN_TO_MM = 25.4


def load(scenario_id: str) -> tuple[dict, str]:
    p = SCEN / f"{scenario_id}.toml"
    if not p.exists():
        raise data.UnknownScenario(scenario_id)
    raw = p.read_bytes()
    return tomllib.loads(raw.decode()), hashlib.sha256(raw).hexdigest()


def v(field):
    """Value of a {value, status, confidence} field, or the raw value."""
    return field["value"] if isinstance(field, dict) and "value" in field else field


def failure_time(s: dict, variant: str | None = None) -> pd.Timestamp:
    var = s["variants"][variant or s["mechanism"]["primary_variant"]]
    return pd.Timestamp(v(var["failure_timestamp_utc"])).tz_convert("UTC").tz_localize(None)


def indiana_daily_rain_mm(s: dict) -> pd.Series:
    r = pd.read_csv(ROOT / s["conditions"]["rain_file"], parse_dates=["time_utc"])
    return r.set_index("time_utc")["precipitation_in"].resample("D").sum(min_count=20) * IN_TO_MM


@dataclass
class Analog:
    station_id: str
    wessex_failure_day: pd.Timestamp  # the Wessex day aligned with the Indiana failure day
    shift_days: int  # Indiana day = Wessex day + shift_days
    sse: float
    storm_ss: float
    weak: bool
    rank: int


def rain_analog(s: dict, wessex_rain: pd.DataFrame, year: int = 2023, rank: int = 0, variant=None) -> Analog:
    """Wessex day whose preceding 7 daily rain totals best match the Indiana 7 days before failure (SSE, mm),
    same calendar month +-1, in `year`. rank=0 is the best match; dev variants use rank i+1 on 2022."""
    fday = failure_time(s, variant).floor("D")
    ind = indiana_daily_rain_mm(s)
    target = ind.reindex(pd.date_range(fday - pd.Timedelta(days=7), periods=7, freq="D")).fillna(0).to_numpy()
    w = wessex_rain.set_index("ts_hour")["mm"].resample("D").sum(min_count=20)
    months = {((fday.month + k - 1) % 12) + 1 for k in (-1, 0, 1)}
    cands = []
    for d in w.index[(w.index.year == year) & w.index.month.isin(months)]:
        win = w.reindex(pd.date_range(d - pd.Timedelta(days=7), periods=7, freq="D"))
        if win.isna().any():
            continue
        cands.append((float(((win.to_numpy() - target) ** 2).sum()), d))
    cands.sort()
    sse, d = cands[rank]
    storm_ss = float((target**2).sum())
    return Analog(
        station_id=str(v(s["station_standin"]["wessex_site"])),
        wessex_failure_day=d,
        shift_days=int((fday - d).days),
        sse=sse,
        storm_ss=storm_ss,
        weak=storm_ss > 0 and sse > 0.5 * storm_ss,
        rank=rank,
    )


def inferred_inflow(events: pd.DataFrame, step: str = "15s") -> pd.Series:
    """Relative inflow in well-volumes/hour from real pump timing, per full cycle (fill + run):
    at steady state the well receives what the pump removes, so I = CI_pump * run / (run + fill), where CI_pump
    (= Q_pump / V) is that pump's median capacity index. Unlike 3600/fill, this stays valid in storms when
    pumps run long and fills are short or missing. 30-min rolling median, forward-filled at most 6 h."""
    c: dict = {}
    cyc = quality.cycles(quality.pair_runs(events, c), c)
    ci_pump = cyc[cyc["valid"]].groupby("pump_id")["ci"].median()
    ok = cyc[(cyc["fill_s"] >= 0) & ~cyc["overlap"] & (cyc["run_s"] >= quality.RUN_MIN_S)].copy()
    run = ok["run_s"].clip(upper=quality.RUN_MAX_S)
    ok["inflow"] = ok["pump_id"].map(ci_pump) * run / (run + ok["fill_s"])
    s = pd.Series(ok["inflow"].to_numpy(), index=ok["start"].to_numpy()).sort_index()
    s = s[~s.index.duplicated()].rolling("30min").median()
    return s.resample(step).mean().ffill(limit=int(6 * 3600 / pd.Timedelta(step).total_seconds()))


def scaled_inflow_gpm(s: dict, analog: Analog, sd: data.StationData, pre_days: int = 30, post_days: int = 2):
    """Analog inflow (gpm) on the Indiana clock, scaled so the stand-in station's median dry-day inflow
    equals dry_weather_inflow_gpm. The same factor applies in storms."""
    rel = inferred_inflow(sd.events)
    daily_rain = sd.rain.set_index("ts_hour")["mm"].resample("D").sum(min_count=20)
    dry_days = daily_rain[daily_rain == 0].index
    rel_day = rel.resample("D").median()
    dry_median = float(rel_day.reindex(dry_days).median())
    factor = float(v(s["conditions"]["dry_weather_inflow_gpm"])) / dry_median
    lo = analog.wessex_failure_day - pd.Timedelta(days=pre_days)
    hi = analog.wessex_failure_day + pd.Timedelta(days=post_days)
    win = rel[(rel.index >= lo) & (rel.index < hi)].interpolate(limit_direction="both")
    out = win * factor
    out.index = out.index + pd.Timedelta(days=analog.shift_days)
    return out, factor


def loss_at(t: pd.DatetimeIndex, onset: pd.Timestamp, failure: pd.Timestamp, loss_24h: float, shape: str):
    """§5.2 ramp: 0 before onset, loss_24h * frac^p up to failure-24h, then held at loss_24h."""
    p = 2.0 if str(shape).startswith("accel") else 1.0
    end = failure - pd.Timedelta(hours=24)
    span = max((end - onset).total_seconds(), 1.0)
    frac = np.clip(np.asarray((t - onset).total_seconds(), dtype=float) / span, 0.0, 1.0)
    out = loss_24h * frac**p
    out[t < onset] = 0.0
    return out
