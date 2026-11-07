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


def _shift(sd: data.StationData, days: int, lo: pd.Timestamp, hi: pd.Timestamp) -> data.StationData:
    """Stand-in data from [lo, hi) on the Wessex clock, moved by whole days onto the Indiana clock (§5.3)."""
    dt = pd.Timedelta(days=days)
    ev = sd.events[sd.events.ts.between(lo, hi, inclusive="left")].assign(ts=lambda x: x.ts + dt)
    lv = sd.level[sd.level.ts.between(lo, hi, inclusive="left")].assign(ts=lambda x: x.ts + dt)
    rn = sd.rain[sd.rain.ts_hour.between(lo, hi, inclusive="left")].assign(ts_hour=lambda x: x.ts_hour + dt)
    return data.StationData(**{**sd.__dict__, "events": ev, "level": lv, "rain": rn})


def level_scale(sd: data.StationData, end: pd.Timestamp) -> tuple[float, float]:
    """§5.4: pump-off maps to the median level at pump stop; storage-full to the trailing 60-day maximum."""
    lv = sd.level[(sd.level.ts < end) & (sd.level.ts >= end - pd.Timedelta(days=60)) & sd.level.in_range]
    stops = sd.events[(sd.events.state == 0) & sd.events.ts.between(end - pd.Timedelta(days=60), end)].ts
    s = lv.set_index("ts")["value"].sort_index()
    at_stop = s.reindex(stops.sort_values(), method="nearest", tolerance=pd.Timedelta(minutes=2)).dropna()
    return float(at_stop.median()), float(s.max())


def case_stream(case_id: str, lookback_days: int = 120):
    """case id -> (StationData on the case clock, truth list, meta). Indiana ids are '<scenario_id>:<A|B>'
    (locked replay: 2023 analog, rank 0); family ids are 'F<n>-<seed>' from evaluate.make_cases."""
    from . import inject, outcome

    if ":" in case_id:
        sid, var = case_id.split(":")
        s, shash = load(sid)
        run, analog, d = outcome.no_warning_run(sid, var)
        sd = data.load(None, sid)
        lo = analog.wessex_failure_day - pd.Timedelta(days=lookback_days)
        hi = analog.wessex_failure_day + pd.Timedelta(days=3)
        st = _shift(sd, analog.shift_days, lo, hi)
        failure, restore = d["failure"], d["restore"]
        l0, l1 = level_scale(st, failure)
        trace = l0 + run.level_frac * (l1 - l0)
        transforms = []
        varspec = s["variants"][var]
        if v(varspec["precursor_type"]) != "none":
            duty = st.events[st.events.state == 1].pump_id.value_counts().index[0]
            onset = failure - pd.Timedelta(days=float(v(varspec["precursor_onset_days_before"])))
            transforms.append(
                {
                    "name": "capacity_loss",
                    "pump": duty,
                    "onset": onset,
                    "failure": failure,
                    "loss_24h": float(v(varspec.get("loss_24h", 0.6))),
                    "shape": v(varspec["precursor_shape"]),
                }
            )
        power_lost = "power" in str(v(varspec["mechanism"])).lower() and var == "A" and "fishers" in sid
        transforms.append(
            {
                "name": "station_trip",
                "start": failure,
                "restore": restore,
                "level_trace": None if power_lost else trace,
                "drop_level": power_lost,
            }
        )
        st, truth = inject.apply(st, transforms, seed=0)
        meta = {
            "origin": "SIMULATED_INCIDENT",
            "scenario_hash": shash,
            "failure_at": failure,
            "restore_at": restore,
            "analog": analog.__dict__,
            "outcome": {"no_system_gal": run.overflow_gal},
            "assumptions": run.assumptions,
        }
        return st, truth, meta
    from . import evaluate as E

    fam = case_id.split("-")[0]
    tier = "dev" if int(case_id.split("-")[1]) < 1000 else "test"
    n = int(case_id.split("-")[1]) - E.TIERS[tier][1] + 1
    case = next((c for c in E.make_cases(tier, {fam: n}) if c.case_id == case_id), None)
    if case is None:
        raise data.UnknownScenario(case_id)
    b = E.build(case, keep_stream=True)
    return b["stream"], [b["truth"]], {"origin": "SYNTHETIC_INJECTION", "case": case}
