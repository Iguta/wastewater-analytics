"""Detector behaviour on real fixtures and synthetic streams (§4.4-4.8, gates G3, G4, G6)."""

import inspect

import numpy as np
import pandas as pd
import pytest

from backend.app import data, detect, features, params

P = params.load()


@pytest.fixture(scope="module")
def r44371():
    s = data.load("44371")
    t = features.daily_table(s.events, s.level, s.rain, "2023-01-01T00:00:00Z", "44371")
    return detect.run(t, P)


def test_real_2022_precursor_escalates(r44371):
    p1 = r44371[r44371.pump_id == "P1"].set_index("day")
    assert p1.loc["2022-05-30", "status"] == "NORMAL"
    assert p1.loc["2022-06-01", "status"] in ("WATCH", "INVESTIGATE")
    assert p1.loc["2022-06-02", "status"] == "INVESTIGATE"
    assert p1.loc["2022-06-02", "incident_id"] == "REAL:44371:P1:CAPACITY_DROP:2022-06-01"


def test_g6_dev_false_escalation_rate(r44371):
    y = r44371[r44371.day.dt.year == 2022]
    inv = y[y.status == "INVESTIGATE"].incident_id.nunique()
    assert inv / 2 / (365 / 180) <= 1.0


def test_warmup_is_insufficient_evidence(r44371):
    assert (r44371[r44371.day < "2022-02-15"].status == "INSUFFICIENT_EVIDENCE").all()


def test_determinism():
    s = data.load("45385")
    t = features.daily_table(s.events, s.level, s.rain, "2022-09-01T00:00:00Z", "45385")
    pd.testing.assert_frame_equal(detect.run(t, P), detect.run(t.copy(), P))


def _daily(ci_by_pump: dict[str, list[float]]) -> pd.DataFrame:
    rows = []
    days = pd.date_range("2022-01-01", periods=len(next(iter(ci_by_pump.values()))), freq="D")
    for pump, cis in ci_by_pump.items():
        for d, ci in zip(days, cis):
            rows.append(
                {
                    "station_id": "9",
                    "pump_id": pump,
                    "day": d,
                    "runs": 50,
                    "valid_cycles": 50,
                    "overlap_share": 0.0,
                    "invalid_share": 0.0,
                    "offline_hours": 0.0,
                    "ci": ci,
                    "run_median_s": 100.0,
                    "fill_median_s": 500.0,
                    "rain_mm": 0.0,
                    "level_flags": [],
                    "quality": "SUFFICIENT",
                }
            )
    return pd.DataFrame(rows)


def test_sibling_inhibition_blocks_station_wide_shift():
    rng = np.random.default_rng(0)
    n = 160
    base = 30 * np.exp(rng.normal(0, 0.02, (2, n)))
    base[:, 120:] *= 0.8  # both pumps drop together: setpoint change, not pump wear
    r = detect.run(_daily({"P1": base[0], "P2": base[1]}), P)
    late = r[r.day >= "2022-05-01"]
    assert not (late.status == "INVESTIGATE").any()
    assert late.station_wide_change.any()
    # ablation without inhibition does escalate: inhibition has a real effect
    r2 = detect.run(_daily({"P1": base[0], "P2": base[1]}), P.with_(inhibition=False))
    assert (r2[r2.day >= "2022-05-01"].status == "INVESTIGATE").any()


def test_single_pump_wear_escalates():
    rng = np.random.default_rng(1)
    n = 160
    base = 30 * np.exp(rng.normal(0, 0.02, (2, n)))
    base[0, 120:] *= 0.75
    r = detect.run(_daily({"P1": base[0], "P2": base[1]}), P)
    assert (r[(r.pump_id == "P1") & (r.day >= "2022-05-01")].status == "INVESTIGATE").any()
    assert not (r[r.pump_id == "P2"].status == "INVESTIGATE").any()


def _stream(minutes: int, end_gap_min: int, level_value=None):
    t0 = pd.Timestamp("2022-03-01")
    ts = pd.date_range(t0, periods=minutes, freq="min")
    lv = pd.DataFrame(
        {
            "signal_id": "L",
            "ts": ts,
            "value": level_value if level_value is not None else 40 + 10 * np.sin(np.arange(minutes) / 9),
            "units": "%",
            "in_range": True,
        }
    )
    starts = ts[::10]
    ev = pd.concat(
        [
            pd.DataFrame({"signal_id": "9_PFFPump1_W", "pump_id": "P1", "ts": starts, "state": 1}),
            pd.DataFrame(
                {
                    "signal_id": "9_PFFPump1_W",
                    "pump_id": "P1",
                    "ts": starts + pd.Timedelta(minutes=2),
                    "state": 0,
                }
            ),
        ]
    ).sort_values("ts")
    as_of = ts[-1] + pd.Timedelta(minutes=end_gap_min)
    return ev, lv, as_of


def test_source_silent_within_10_minutes_via_level_heartbeat():
    ev, lv, as_of = _stream(3000, 10)
    out = detect.realtime(ev, lv, as_of, P)
    assert any(f["type"] == "SOURCE_SILENT" for f in out)
    ev, lv, as_of = _stream(3000, 6)  # a 6-min dropout is common on real data and must not alarm
    assert not any(f["type"] == "SOURCE_SILENT" for f in detect.realtime(ev, lv, as_of, P))


def test_high_level_fires_and_has_no_inhibition_path():
    v = 40 + 10 * np.sin(np.arange(3000) / 9)
    v[-20:] = 99.0
    ev, lv, as_of = _stream(3000, 1, v)
    assert any(f["type"] == "HIGH_LEVEL" for f in detect.realtime(ev, lv, as_of, P))
    src = inspect.getsource(detect.realtime)
    assert "rain" not in src and "common" not in src  # G4: nothing can mute HIGH_LEVEL


def test_level_flatline_is_sensor_fault():
    v = 40 + 10 * np.sin(np.arange(3000) / 9)
    v[-500:] = 42.0
    ev, lv, as_of = _stream(3000, 1, v)
    out = detect.realtime(ev, lv, as_of, P)
    assert any(f["type"] == "SENSOR_FAULT" and "LEVEL_FLATLINE" in f["flags"] for f in out)


def test_level_gap_with_pumps_running_is_sensor_fault_not_offline():
    ev, lv, as_of = _stream(3000, 1)
    lv = lv[lv.ts < lv.ts.max() - pd.Timedelta(minutes=30)]  # level silent 30 min, pumps keep cycling
    out = detect.realtime(ev, lv, as_of, P)
    types = {f["type"]: f for f in out}
    assert "SOURCE_SILENT" not in types
    assert "LEVEL_GAP" in types["SENSOR_FAULT"]["flags"]
    assert types["HIGH_LEVEL"]["status"] == "UNKNOWN"


def test_offline_hours_count_only_silent_time():
    from backend.app import features

    ts = pd.Series(pd.to_datetime(["2022-01-01 00:00", "2022-01-01 01:00", "2022-01-01 01:01"]))
    off = features.offline_hours_by_day(
        ts, pd.Timestamp("2022-01-01"), pd.Timestamp("2022-01-01 02:00"), pd.Timedelta(minutes=5)
    )
    # 00:05-01:00 silent (55 min) + 01:06-02:00 (54 min), at a 5-min silence threshold
    assert abs(off[pd.Timestamp("2022-01-01")] - (55 + 54) / 60) < 1e-9


def test_large_shared_drop_escalates_station_on_size():
    rng = np.random.default_rng(2)
    n = 160
    base = 30 * np.exp(rng.normal(0, 0.02, (2, n)))
    base[:, 120:] *= 0.65  # both pumps restricted 35%: serious whatever the cause
    r = detect.run(_daily({"P1": base[0], "P2": base[1]}), P)
    st = r[r.pump_id == "P1"].set_index("day").station_wide_status
    assert st["2022-05-02"] != "INVESTIGATE" and st["2022-05-03"] == "INVESTIGATE"
    # per-pump status stays inhibited until the baseline starts absorbing the shift (G = 14 days, §4.4 known limit)
    early = r[r.day.between("2022-05-01", "2022-05-14")]
    assert not (early.status == "INVESTIGATE").any()


def test_min_effect_blocks_investigate_on_tiny_precise_drop():
    rng = np.random.default_rng(3)
    n = 160
    base = 30 * np.exp(rng.normal(0, 0.003, (2, n)))  # very low scatter
    base[0, 120:] *= 0.96  # -4%: statistically clear, practically small
    r = detect.run(_daily({"P1": base[0], "P2": base[1]}), P)
    p1 = r[(r.pump_id == "P1") & (r.day >= "2022-05-01")]
    assert (p1.status == "WATCH").any() and not (p1.status == "INVESTIGATE").any()
