"""§5.7 proxy-event detection on synthetic detect.run-shaped tables."""

import pandas as pd

from backend.scripts.proxy_events import episodes, is_rotation, silences


def table(p1_runs, p2_runs, start="2022-03-01", incident_day=None, station_wide=None):
    days = pd.date_range(start, periods=len(p1_runs), freq="D")
    rows = []
    for i, (d, a, b) in enumerate(zip(days, p1_runs, p2_runs)):
        inc = (
            f"REAL:9:P1:CAPACITY_DROP:{incident_day}"
            if incident_day and d >= pd.Timestamp(incident_day)
            else None
        )
        sw = station_wide[i] if station_wide else "NORMAL"
        for pump, runs, iid in (("P1", a, inc), ("P2", b, None)):
            rows.append(
                {
                    "station_id": "9",
                    "pump_id": pump,
                    "day": d,
                    "runs": runs,
                    "base_runs_median": 50.0,
                    "incident_id": iid,
                    "station_wide_status": sw,
                }
            )
    return pd.DataFrame(rows)


OUT3 = ([40, 40, 0, 0, 0, 40], [40, 40, 80, 80, 80, 40])


def test_busy_pump_out_three_days_with_busy_sibling_is_one_episode():
    e = episodes(table(*OUT3))
    assert len(e) == 1 and e[0]["start"] == "2022-03-03" and e[0]["end"] == "2022-03-05" and e[0]["days"] == 3
    assert e[0]["tier"] == "dev" and not e[0]["preceded"]


def test_sibling_not_busy_is_no_episode():
    assert episodes(table([40, 0, 0, 0, 40], [40, 5, 5, 5, 40])) == []


def test_one_day_gap_is_no_episode():
    assert episodes(table([40, 40, 0, 40, 40], [40, 40, 80, 40, 40])) == []


def test_episode_overlapping_a_6h_silence_is_excluded():
    gap = [(pd.Timestamp("2022-03-04 02:00"), pd.Timestamp("2022-03-04 09:00"))]
    assert episodes(table(*OUT3), gap) == []
    ts = pd.Series(pd.to_datetime(["2022-03-04 02:00", "2022-03-04 09:00", "2022-03-04 09:05"]))
    assert silences(ts) == gap


def test_episode_overlapping_aug_2023_window_is_excluded():
    assert episodes(table(*OUT3, start="2023-08-16")) == []


def test_preceded_by_any_open_watch_or_investigate():
    e = episodes(table([40, 40, 40, 0, 0, 40], [40, 40, 40, 80, 80, 40], incident_day="2022-03-02"))
    assert e[0]["preceded"] and e[0]["first_alert_day"] == "2022-03-02" and e[0]["lead_days"] == 2
    sw = ["NORMAL", "WATCH", "WATCH", "WATCH", "WATCH", "NORMAL"]
    e = episodes(table([40, 40, 40, 0, 0, 40], [40, 40, 40, 80, 80, 40], station_wide=sw))
    assert e[0]["preceded"] and e[0]["first_alert_day"] == "2022-03-02"


def test_rotation_flag_when_most_episodes_last_exactly_2_days():
    two, three = {"days": 2}, {"days": 3}
    assert is_rotation([two, two, three])
    assert not is_rotation([two, three])
    assert not is_rotation([])
