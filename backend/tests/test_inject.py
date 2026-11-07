"""Fault injection transforms (§5.2) and truth isolation (§5.8)."""

import inspect

import pandas as pd
import pytest

from backend.app import data, detect, features, inject, quality


@pytest.fixture(scope="module")
def sd():
    s = data.load("44371")
    lo, hi = pd.Timestamp("2022-08-01"), pd.Timestamp("2022-12-01")
    return data.StationData(
        **{
            **s.__dict__,
            "events": s.events[s.events.ts.between(lo, hi)],
            "level": s.level[s.level.ts.between(lo, hi)],
        }
    )


def _ci(sd, pump, lo, hi):
    c: dict = {}
    cyc = quality.cycles(quality.pair_runs(sd.events, c), c)
    m = (cyc.pump_id == pump) & cyc.start.between(lo, hi) & cyc.valid
    return cyc[m].ci.median()


def test_capacity_loss_lowers_ci_and_caps_runs(sd):
    on, fail = pd.Timestamp("2022-10-01"), pd.Timestamp("2022-10-21")
    out, truth = inject.capacity_loss(sd, "P1", on, fail, 0.3)
    before = _ci(sd, "P1", fail - pd.Timedelta(days=3), fail - pd.Timedelta(days=1))
    after = _ci(
        out,
        "P1",
        fail - pd.Timedelta(days=3) + pd.Timedelta(hours=truth["clock_shift_h"]),
        fail - pd.Timedelta(days=1) + pd.Timedelta(hours=truth["clock_shift_h"]),
    )
    assert after < 0.9 * before
    c: dict = {}
    runs = quality.pair_runs(out.events, c)
    shifted = fail + pd.Timedelta(hours=truth["clock_shift_h"])
    injected = runs[(runs.pump_id == "P1") & runs.start.between(on, shifted)]
    assert injected.run_s.max() <= quality.RUN_MAX_S  # real raw LONG_RUNs elsewhere are untouched
    assert truth["sibling"] == "P2"


def test_transient_stays_within_one_output_day(sd):
    day = pd.Timestamp("2022-10-05")
    out, _ = inject.transient(sd, "P1", day, 0.5)
    t = features.daily_table(out.events, out.level, out.rain, "2022-10-12", "44371")
    clean = features.daily_table(sd.events, sd.level, sd.rain, "2022-10-12", "44371")
    d = t.set_index(["pump_id", "day"]).ci / clean.set_index(["pump_id", "day"]).ci
    assert d.loc[("P1", day)] < 0.9
    assert d.loc[("P1", day + pd.Timedelta(days=2))] > 0.95


def test_outage_removes_events_and_level(sd):
    s = pd.Timestamp("2022-10-05 06:00")
    out, _ = inject.outage(sd, s, 3)
    assert not out.events.ts.between(s, s + pd.Timedelta(hours=3), inclusive="left").any()
    assert not out.level.ts.between(s, s + pd.Timedelta(hours=3), inclusive="left").any()


def test_truth_isolation():
    """§5.8: features and detect never import inject or read truth."""
    import ast

    for mod in (features, detect):
        tree = ast.parse(inspect.getsource(mod))
        imported = {
            a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names
        }
        assert "inject" not in imported and "evaluate" not in imported
        args = {a.arg for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) for a in n.args.args}
        assert "truth" not in args
