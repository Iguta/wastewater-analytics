"""Outcome simulator: mass balance and gate G7 (§5.4, §6.3)."""

import numpy as np
import pandas as pd
import pytest

from backend.app import outcome

SCENARIOS = ["bloomington_morningside_2024_04_11", "fishers_bowline_2009_01_20"]


def test_mass_balance_overflow_equals_excess_inflow():
    idx = pd.date_range("2022-01-01", periods=4 * 120, freq="15s")  # 2 h
    inflow = pd.Series(100.0, index=idx)
    caps = pd.DataFrame({"duty": 0.0, "standby": 0.0}, index=idx)  # station down the whole time
    run = outcome.simulate(inflow, caps, {"storage_gal": 1500})
    assert abs(run.overflow_gal - (100 * 120 - 1500)) < 1e-6


def test_standby_joins_only_when_duty_cannot_keep_up():
    idx = pd.date_range("2022-01-01", periods=400, freq="15s")
    caps = pd.DataFrame({"duty": 80.0, "standby": 80.0}, index=idx)
    assert outcome.simulate(pd.Series(150.0, index=idx), caps, {"storage_gal": 100}).overflow_gal == 0
    caps["standby"] = 0.0
    assert outcome.simulate(pd.Series(150.0, index=idx), caps, {"storage_gal": 100}).overflow_gal > 0


@pytest.mark.parametrize("sid", SCENARIOS)
@pytest.mark.parametrize("variant", ["A", "B"])
def test_g7_no_warning_run_reproduces_record(sid, variant):
    run, _analog, d = outcome.no_warning_run(sid, variant)
    tol = d["tolerance_pct"] / 100
    assert d["target_gal"] * (1 - tol) <= run.overflow_gal <= d["target_gal"] * (1 + tol)
    # the only spill is the incident itself: nothing before the failure
    pre = run.level_frac[run.level_frac.index < d["failure"]]
    assert not np.any(pre.to_numpy() >= 1.0)
    assert d["failure"] <= run.overflow_start <= d["restore"]


def test_precursor_loss_is_not_capped():
    """The §5.1 sweep needs loss_24h = 0.8 to reach the simulator unchanged."""
    _r60, _a, _d60 = outcome.no_warning_run(SCENARIOS[0], "A", loss_24h=0.6)
    r80, _a, _d80 = outcome.no_warning_run(SCENARIOS[0], "A", loss_24h=0.8)
    assert r80.overflow_gal >= _r60.overflow_gal
