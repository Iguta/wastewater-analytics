"""§5.7 proxy-event detection on synthetic detect.run-shaped tables."""

import pandas as pd

from backend.scripts.proxy_events import episodes


def table(p1_runs, p2_runs, base=50.0, incident_day=None):
    days = pd.date_range("2022-03-01", periods=len(p1_runs), freq="D")
    rows = []
    for d, a, b in zip(days, p1_runs, p2_runs):
        inc = (
            f"REAL:9:P1:CAPACITY_DROP:{incident_day}"
            if incident_day and d >= pd.Timestamp(incident_day)
            else None
        )
        rows.append(
            {
                "station_id": "9",
                "pump_id": "P1",
                "day": d,
                "runs": a,
                "base_runs_median": base,
                "incident_id": inc,
            }
        )
        rows.append(
            {
                "station_id": "9",
                "pump_id": "P2",
                "day": d,
                "runs": b,
                "base_runs_median": base,
                "incident_id": None,
            }
        )
    return pd.DataFrame(rows)


def test_busy_pump_out_three_days_with_busy_sibling_is_one_episode():
    e = episodes(table([40, 40, 0, 0, 0, 40], [40, 40, 80, 80, 80, 40]))
    assert len(e) == 1 and e[0]["start"] == "2022-03-03" and e[0]["end"] == "2022-03-05"
    assert e[0]["tier"] == "dev" and not e[0]["preceded"]


def test_sibling_not_busy_is_no_episode():
    assert episodes(table([40, 0, 0, 0, 40], [40, 5, 5, 5, 40])) == []


def test_one_day_gap_is_no_episode():
    assert episodes(table([40, 40, 0, 40, 40], [40, 40, 80, 40, 40])) == []


def test_preceded_by_capacity_drop_opened_a_day_before():
    e = episodes(table([40, 40, 40, 0, 0, 40], [40, 40, 40, 80, 80, 40], incident_day="2022-03-02"))
    assert e[0]["preceded"] and e[0]["first_alert_day"] == "2022-03-02" and e[0]["lead_days"] == 2
    assert e[0]["timely"]
