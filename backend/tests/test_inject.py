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


def test_station_trip_removes_runs_and_simulates_level(sd):
    s, r = pd.Timestamp("2022-10-05 06:00"), pd.Timestamp("2022-10-05 09:00")
    trace = pd.Series(50.0, index=pd.date_range(s, r, freq="15s"))
    out, truth = inject.station_trip(sd, s, r, level_trace=trace)
    assert not out.events.ts.between(s, r, inclusive="left").any()
    w = out.level[out.level.ts.between(s, r, inclusive="left")]
    assert len(w) > 100 and (w.value == 50.0).all() and truth["level"] == "SIMULATED"
    out2, t2 = inject.station_trip(sd, s, r, drop_level=True)
    assert not out2.level.ts.between(s, r, inclusive="left").any() and t2["level"] == "deleted"


def test_apply_runs_transforms_in_order_and_returns_truth(sd):
    s = pd.Timestamp("2022-10-05 06:00")
    out, truth = inject.apply(
        sd,
        [
            {"name": "outage", "start": s, "hours": 2},
            {"name": "sensor_fault", "kind": "duplicate_rows", "start": s},
        ],
        seed=3,
    )
    assert [t["transform"] for t in truth] == ["outage", "sensor_fault"]
    assert len(out.events) > len(sd.events[~sd.events.ts.between(s, s + pd.Timedelta(hours=2))])


def test_fishers_a_replay_goes_silent_within_10_minutes():
    from backend.app import detect, params, scenarios

    st, truth, meta = scenarios.case_stream("fishers_bowline_2009_01_20:A")
    f = meta["failure_at"]
    assert truth[-1]["transform"] == "station_trip" and truth[-1]["level"] == "deleted"
    out = detect.realtime(st.events, st.level, f + pd.Timedelta(minutes=10), params.load())
    assert any(x["type"] == "SOURCE_SILENT" for x in out)


def test_test_tier_log_is_append_only_and_records_v2_once():
    import json

    from backend.app import evaluate

    runs = [json.loads(x) for x in evaluate.TEST_RUNS.read_text().splitlines() if x.strip()]
    v2 = [r for r in runs if r["model_version"] == "dragonfly-ci-v2-tuned"]
    assert len(v2) == 1 and not v2[0]["forced"] and "G5" in v2[0]["gates"]
