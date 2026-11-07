"""Daily table on the real committed fixtures: rain invariance (§11.1) and no lookahead."""

import pandas as pd
import pytest

from backend.app import data, features


@pytest.fixture(scope="module")
def s44371():
    return data.load("44371")


@pytest.fixture(scope="module")
def t44371(s44371):
    s = s44371
    return features.daily_table(s.events, s.level, s.rain, "2023-01-01T00:00:00Z", "44371")


def test_columns_and_complete_days_only(t44371):
    assert list(t44371.columns) == features.COLUMNS
    assert t44371.day.max() == pd.Timestamp("2022-12-31")
    assert set(t44371.quality) <= {"SUFFICIENT", "PARTIAL", "INSUFFICIENT", "SOURCE_OFFLINE"}


def test_ci_rain_invariance(t44371):
    """On 44371 2022, wet (>=10 mm) / dry (0 mm) median CI is within 0.95-1.05 per pump."""
    t = t44371[(t44371.quality == "SUFFICIENT")]
    for pump, g in t.groupby("pump_id"):
        wet, dry = g[g.rain_mm >= 10], g[g.rain_mm == 0]
        assert len(wet) >= 20 and len(dry) >= 50
        ratio = wet.ci.median() / dry.ci.median()
        assert 0.95 <= ratio <= 1.05, (pump, ratio)
        # raw run time is NOT rain-invariant, which is the point of the index
        assert wet.run_median_s.median() / dry.run_median_s.median() > 1.1


def test_real_2022_precursor_visible(t44371):
    p1 = t44371[t44371.pump_id == "P1"].set_index("day").ci
    assert p1["2022-06-01"] / p1["2022-05-10":"2022-05-30"].median() < 0.6


def test_no_lookahead(s44371):
    """Rows for days before the cutoff are identical whether or not later data exists."""
    s = s44371
    cut = "2022-07-01T00:00:00Z"
    a = features.daily_table(s.events, s.level, s.rain, cut, "44371")
    later = s.events[s.events.ts < pd.Timestamp("2022-07-01")]
    lv = s.level[s.level.ts < pd.Timestamp("2022-07-01")]
    b = features.daily_table(later, lv, s.rain, cut, "44371")
    pd.testing.assert_frame_equal(a, b)
    assert a.day.max() == pd.Timestamp("2022-06-30")
