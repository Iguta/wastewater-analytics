"""Per-pump pairing and §3.5 quality rules on adversarial event streams."""

import pandas as pd

from backend.app import quality


def ev(rows):
    return quality.parse_events(pd.DataFrame(rows, columns=["signal_id", "ts", "value"]), {})


P1, P2 = "9_PFFPump1_WASTE_X", "9_PFFPump2_WASTE_Y"


def test_pairing_never_crosses_pumps():
    e = ev(
        [
            (P1, "2022-01-01 00:00:00", "1"),
            (P2, "2022-01-01 00:00:30", "0"),  # P2 stop with no P2 start: must not close P1's run
            (P1, "2022-01-01 00:02:00", "0"),
        ]
    )
    c = {}
    runs = quality.pair_runs(e, c)
    assert list(runs.pump_id) == ["P1"] and list(runs.run_s) == [120.0]
    assert c["LEADING_STOP"] == 1


def test_repeated_start_and_stop_keep_first():
    e = ev(
        [
            (P1, "2022-01-01 00:00:00", "1"),
            (P1, "2022-01-01 00:00:10", "1"),  # repeated start -> keep first
            (P1, "2022-01-01 00:01:40", "0"),
            (P1, "2022-01-01 00:01:50", "0"),  # repeated stop -> keep first
        ]
    )
    c = {}
    runs = quality.pair_runs(e, c)
    assert list(runs.run_s) == [100.0]
    assert c["REPEATED_START"] == 1 and c["REPEATED_STOP"] == 1


def test_duplicates_bad_timestamps_and_open_run_counted():
    c = {}
    e = quality.parse_events(
        pd.DataFrame(
            [
                (P1, "2022-01-01 00:00:00", "1"),
                (P1, "2022-01-01 00:00:00", "1"),
                (P1, "not a time", "0"),
                (P1, "2022-01-01 00:02:00", "0"),
                (P1, "2022-01-01 00:10:00", "1"),  # never stopped
            ],
            columns=["signal_id", "ts", "value"],
        ),
        c,
    )
    runs = quality.pair_runs(e, c)
    assert c["DUPLICATE_ROW"] == 1 and c["BAD_TIMESTAMP"] == 1 and c["OPEN_RUN"] == 1
    assert len(runs) == 1


def test_capacity_index_and_overlap():
    e = ev(
        [
            (P1, "2022-01-01 00:00:00", "1"),
            (P1, "2022-01-01 00:01:40", "0"),
            (P2, "2022-01-01 00:10:00", "1"),
            (P2, "2022-01-01 00:11:40", "0"),
            (P1, "2022-01-01 00:11:00", "1"),
            (P1, "2022-01-01 00:12:00", "0"),  # starts during P2 run
        ]
    )
    c = {}
    cyc = quality.cycles(quality.pair_runs(e, c), c)
    p2 = cyc[cyc.pump_id == "P2"].iloc[0]
    assert p2.fill_s == 500 and p2.valid and abs(p2.ci - (3600 / 100 + 3600 / 500)) < 1e-9
    assert cyc[cyc.start == pd.Timestamp("2022-01-01 00:11:00")].overlap.item()
    assert c["OVERLAP"] == 1


def test_level_out_of_range_flagged_not_dropped():
    c = {}
    lv = quality.parse_level(
        pd.DataFrame(
            [
                ("L", "2022-01-01 00:00:00", "-1", "%"),
                ("L", "2022-01-01 00:01:00", "50", "%"),
                ("L", "2022-01-01 00:02:00", "106", "%"),
            ],
            columns=["signal_id", "ts", "value", "units"],
        ),
        c,
    )
    assert len(lv) == 3 and lv.in_range.sum() == 1 and c["LEVEL_OUT_OF_RANGE"] == 2
