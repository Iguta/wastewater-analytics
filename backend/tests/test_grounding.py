import json

import pytest

from backend.app.grounding import check

TOOL = json.dumps(
    {
        "status": "INVESTIGATE",
        "station_id": "44371",
        "as_of_utc": "2022-06-03T00:00:00Z",
        "pumps": [
            {
                "pump_id": "P1",
                "status": "INVESTIGATE",
                "capacity_change_pct": -42.33700761825979,
                "valid_cycles": 42,
            }
        ],
        "queue": [{"alert_id": "REAL:44371:P1:CAPACITY_DROP:2022-06-01", "days_open": 2}],
    }
)
GOOD = "Station 44371 is INVESTIGATE as of 2022-06-03. P1 capacity is down -42.3% over 2 days (REAL:44371:P1:CAPACITY_DROP:2022-06-01), 42 valid cycles."


def test_grounded_answer_passes():
    assert check(GOOD, [TOOL]).passed


def test_invented_number_fails():
    g = check(GOOD.replace("42 valid", "57 valid"), [TOOL])
    assert not g.passed and g.unmatched_numbers == ["57"]


def test_wrong_status_fails():
    g = check(GOOD.replace("INVESTIGATE", "NORMAL"), [TOOL])
    assert not g.passed and "NORMAL" in g.unmatched_numbers


@pytest.mark.parametrize(
    "word", ["probability", "will fail", "confirmed", "guarantee", "definitely", "prevent"]
)
def test_each_forbidden_phrase_fails(word):
    g = check(f"{GOOD} It is {word}.", [TOOL])
    assert not g.passed and g.forbidden_phrases == [word]


def test_ids_dates_and_labels_are_ignored():
    assert check(
        "P3 at 44371 on 2022-06-03T00:00:00Z, alert REAL:45385:P3:X:2031-02-09, case F2-0.", [TOOL]
    ).passed


def test_status_must_match_the_pump_it_names():
    tools = [
        '{"pumps": [{"pump_id": "P1", "status": "NORMAL"}, {"pump_id": "P2", "status": "INVESTIGATE"}], "status": "INVESTIGATE"}'
    ]
    assert not check("P1 is INVESTIGATE.", tools).passed
    assert check("P2 is INVESTIGATE. P1 is NORMAL.", tools).passed
    assert check("The station is INVESTIGATE.", tools).passed


def test_mixed_case_status_is_checked():
    assert not check("P1 is Normal.", [TOOL]).passed


def test_numbers_parse_commas_and_ranges():
    tool = json.dumps({"gal": 1234, "a": 2, "b": 3})
    assert check("1,234 gal, 2-3 days.", [tool]).passed
    assert not check("2-7 days.", [tool]).passed


def test_ids_and_dates_are_not_numbers():
    tool = json.dumps({"station_id": "44371", "day": "2022-06-03", "valid_cycles": 42})
    assert not check("17 cycles", [tool]).passed and not check("2 cycles", [tool]).passed
    assert not check("on 2022-06-04", [tool]).passed
    assert check("44371 on 2022-06-03 had 42 cycles", [tool]).passed


def test_only_returned_stations_are_allowed():
    tool = json.dumps({"station_id": "44371"})
    assert check("Station 44371.", [tool]).passed
    assert not check("Station 45385.", [tool]).passed


def test_forbidden_uses_word_boundaries():
    assert check("Prevention checks are listed.", [TOOL]).passed
    assert not check("Prevent it.", [TOOL]).passed
