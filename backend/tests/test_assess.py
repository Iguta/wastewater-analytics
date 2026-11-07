from datetime import datetime, timezone

import pytest

from backend.app import assess, data, explain
from backend.app.contracts import Finding, PumpState

AS_OF = datetime(2022, 6, 3, tzinfo=timezone.utc)
BANNED = ["probability", "will fail", "confirmed", "saved", "prevented", "would have"]


def test_p1_precursor_is_flagged_at_44371():
    a = assess.assess_station("44371", AS_OF)
    p1 = next(p for p in a.pumps if p.pump_id == "P1")
    assert p1.status in ("WATCH", "INVESTIGATE")
    assert a.queue[0].alert_id.startswith("REAL:44371:P1:CAPACITY_DROP:")
    assert not any(w in a.explanation.lower() for w in BANNED)


def test_evidence_round_trip():
    a = assess.assess_station("44371", AS_OF)
    e = assess.get_evidence(a.queue[0].alert_id, AS_OF)
    assert e.finding == a.queue[0] and e.trace and e.trace[-1].day.isoformat() == "2022-06-02"
    assert e.work_order.evidence_alert_id == e.alert_id
    assert e.transitions and not any(w in e.work_order.title.lower() for w in BANNED)


def test_evidence_unknown_before_it_opens():
    alert = assess.assess_station("44371", AS_OF).queue[0].alert_id
    with pytest.raises(assess.AssessError) as err:
        assess.get_evidence(alert, datetime(2022, 5, 1, tzinfo=timezone.utc))
    assert err.value.error.code == "UNKNOWN_ALERT"


def test_no_lookahead(monkeypatch):
    full = assess.assess_station("44371", AS_OF).model_dump()
    real_load = data.load

    def cut(station_id, scenario_id=None):
        sd = real_load(station_id, scenario_id)
        sd.events = sd.events[sd.events["ts"] < "2022-06-03"]
        sd.level = sd.level[sd.level["ts"] < "2022-06-03"]
        sd.rain = sd.rain[sd.rain["ts_hour"] < "2022-06-03"]
        return sd

    monkeypatch.setattr(data, "load", cut)
    assess._bundle.cache_clear()
    assess.assess_station.cache_clear()
    assert assess.assess_station("44371", AS_OF).model_dump() == full


def test_scenario_blind():
    # Scenario truth never reaches the detector: scenarios are refused until inject exists.
    with pytest.raises(assess.AssessError) as err:
        assess.assess_station("44371", AS_OF, "bloomington_morningside_2024_04_11:A")
    assert err.value.error.code == "NOT_AVAILABLE"


@pytest.mark.parametrize(
    "call, code",
    [
        (lambda: assess.assess_station("99999", AS_OF), "UNKNOWN_STATION"),
        (lambda: assess.assess_station("44371", AS_OF, "nope:A"), "UNKNOWN_SCENARIO"),
        (
            lambda: assess.assess_station("44371", datetime(2025, 1, 1, tzinfo=timezone.utc)),
            "AS_OF_OUT_OF_RANGE",
        ),
        (lambda: assess.parse_time("2022-06-03T00:00:00"), "BAD_TIMESTAMP"),
        (lambda: assess.replay_case("F9-1"), "UNKNOWN_CASE"),
        (lambda: assess.replay_case("F1-1003"), "NOT_AVAILABLE"),
    ],
)
def test_bad_input_carries_a_tool_error(call, code):
    with pytest.raises(assess.AssessError) as err:
        call()
    assert err.value.error.code == code


def test_timeline_days():
    t = assess.timeline(
        "44371", None, datetime(2022, 6, 1, tzinfo=timezone.utc), datetime(2022, 6, 3, tzinfo=timezone.utc)
    )
    # Only days completed before `end`: 06-03 itself is not over at 06-03T00:00, so it must not appear.
    assert [d.day.isoformat() for d in t] == ["2022-06-01", "2022-06-02"]
    assert t[-1].station_status in ("WATCH", "INVESTIGATE")


def test_explanation_has_no_banned_word_for_every_finding_type():
    for kind in explain.CHECKLISTS:
        f = Finding(
            alert_id="REAL:44371:P1:" + kind + ":2022-06-01", type=kind, pump_id="P1", status="WATCH", priority=1,
            opened_on="2022-06-01", since_utc="2022-06-01T00:00:00Z", days_open=2, observed=1.0, expected=2.0,
            units="per hour", change_pct=-50.0, summary="s", possible_causes=[], inspection=[],
        )  # fmt: skip
        p = PumpState(
            pump_id="P1", status="WATCH", quality="SUFFICIENT", ci_today=1.0, ci_baseline=2.0, capacity_change_pct=-50.0,
            cusum=3.0, valid_cycles=30, runs=40, run_median_s=100.0, expected_run_s=None,
        )  # fmt: skip
        texts = [explain.explanation("44371", "WATCH", f, p, ["x"]), explain.explanation("44371", "WATCH", f, None, []),
                 explain.explanation("44371", "NORMAL", None, None, []), " ".join(explain.work_order(f, "44371").checks)]  # fmt: skip
        assert not any(w in t.lower() for t in texts for w in BANNED)
