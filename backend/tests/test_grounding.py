import json

import pytest

from backend.app.grounding import check

TOOL = json.dumps(
    {
        "status": "INVESTIGATE",
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
        "P3 at 45385 on 2031-02-09T00:00:00Z, alert REAL:45385:P3:X:2031-02-09, case F2-0.", [TOOL]
    ).passed
