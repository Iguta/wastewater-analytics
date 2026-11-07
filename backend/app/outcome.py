"""Wet-well mass balance in gallons (§5.4). Used only for overflow volume and the simulated level trace.

Every physical number comes from the scenario file. Continuous-pumping approximation at a 15 s step:
the duty pump runs first; the standby joins when the duty pump alone cannot keep the level falling.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import scenarios
from .scenarios import v


@dataclass
class OutcomeRun:
    overflow_gal: float
    overflow_start: pd.Timestamp | None
    overflow_end: pd.Timestamp | None
    overflow_minutes: float
    level_frac: pd.Series  # stored volume / usable storage (1.0 = full, overflowing)
    assumptions: list[str] = field(default_factory=list)


def simulate(inflow: pd.Series, capacities: pd.DataFrame, spec: dict) -> OutcomeRun:
    """inflow: gpm on a regular index. capacities: gpm per pump on the same index, duty pump first.
    spec: {"storage_gal": float}."""
    dt_min = (inflow.index[1] - inflow.index[0]).total_seconds() / 60
    storage = float(spec["storage_gal"])
    q = inflow.to_numpy(dtype=float)
    cap = capacities.reindex(inflow.index).fillna(0.0).to_numpy(dtype=float)
    duty, rest = cap[:, 0], cap[:, 1:].sum(axis=1) if cap.shape[1] > 1 else np.zeros(len(q))
    vol, over = 0.0, 0.0
    level = np.empty(len(q))
    spill = np.zeros(len(q), dtype=bool)
    for i in range(len(q)):
        vol += q[i] * dt_min
        avail = (
            duty[i] if duty[i] > q[i] else duty[i] + rest[i]
        )  # standby joins if duty can't keep level falling
        vol -= min(vol, avail * dt_min)
        if vol > storage:
            over += vol - storage
            vol = storage
            spill[i] = True
        level[i] = vol / storage
    idx = inflow.index
    start = idx[spill.argmax()] if spill.any() else None
    end = idx[len(spill) - 1 - spill[::-1].argmax()] if spill.any() else None
    return OutcomeRun(
        overflow_gal=over,
        overflow_start=start,
        overflow_end=end,
        overflow_minutes=float(spill.sum() * dt_min),
        level_frac=pd.Series(level, index=idx),
    )


def no_warning_run(
    scenario_id: str,
    variant: str | None = None,
    year: int = 2023,
    rank: int = 0,
    loss_24h: float | None = None,
):
    """The scenario's no-warning outcome: capacity follows the variant's precursor, 0 from failure until
    outage_duration_min later. Returns (OutcomeRun, analog, details).

    loss_24h is the precursor loss held for the last 24 h (§5.2), read from the variant's loss_24h field unless
    the §5.1 sweep passes 0.4 / 0.6 / 0.8. The variant's
    capacity_lost_pct_at_failure (100) is the trip itself, applied from failure_timestamp_utc."""
    from . import data

    s, _ = scenarios.load(scenario_id)
    var_id = variant or s["mechanism"]["primary_variant"]
    var = s["variants"][var_id]
    sd = data.load(None, scenario_id)
    analog = scenarios.rain_analog(s, sd.rain, year=year, rank=rank, variant=var_id)
    inflow, factor = scenarios.scaled_inflow_gpm(s, analog, sd)
    failure = scenarios.failure_time(s, var_id)
    restore = failure + pd.Timedelta(minutes=float(v(s["outcome"]["outage_duration_min"])))
    pump_cap = float(v(s["station_standin"]["pump_capacity_gpm_each"]))
    if v(var["precursor_type"]) == "none":
        loss_24h = 0.0
    elif loss_24h is None:  # the locked file's value; the §5.1 sweep passes its own
        loss_24h = float(v(var["loss_24h"]))
    onset = failure - pd.Timedelta(days=float(v(var["precursor_onset_days_before"])))
    t = inflow.index
    duty = pump_cap * (1 - scenarios.loss_at(t, onset, failure, loss_24h, v(var["precursor_shape"])))
    standby = np.full(len(t), pump_cap)
    out = (t >= failure) & (t < restore)
    duty[out] = 0.0
    standby[out] = 0.0  # every scenario variant loses all station capacity at failure
    caps = pd.DataFrame({"duty": duty, "standby": standby}, index=t)
    run = simulate(
        inflow, caps, {"storage_gal": float(v(s["station_standin"]["wet_well_usable_storage_gal"]))}
    )
    details = {
        "variant": var_id,
        "failure": failure,
        "restore": restore,
        "inflow_scale_gpm_per_wv_h": factor,
        "inflow_during_outage_gpm": float(inflow[(t >= failure) & (t < restore)].mean()),
        "target_gal": float(v(s["outcome"]["overflow_volume_gal"])),
        "tolerance_pct": float(s["outcome"]["overflow_volume_tolerance_pct"]),
    }
    run.assumptions = [
        f"rain analog: Wessex {analog.station_id} {analog.wessex_failure_day.date()} (shift {analog.shift_days} d)"
        + (f", weak: SSE {100 * analog.sse / analog.storm_ss:.0f}% of the storm" if analog.weak else ""),
        f"inflow scaled so the median dry-day inflow = {v(s['conditions']['dry_weather_inflow_gpm'])} gpm",
        f"storage {v(s['station_standin']['wet_well_usable_storage_gal'])} gal, pumps {pump_cap} gpm each",
    ]
    return run, analog, details
