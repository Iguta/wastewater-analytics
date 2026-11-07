from datetime import datetime, timedelta, timezone

import pytest

from backend.app import assess, data, explain, scenarios
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


def test_scenario_blind(monkeypatch):
    # A scenario id selects input data, never an outcome: two ids given the same stream answer the same.
    sd = data.load("44371")
    monkeypatch.setattr(
        scenarios, "case_stream", lambda _id: (sd, [{"secret": 1}], {"origin": "SIMULATED_INCIDENT"})
    )
    assess._case.cache_clear()
    ids = ("bloomington_morningside_2024_04_11:A", "bloomington_morningside_2024_04_11:B")
    a, b = (assess.assess_station("44371", AS_OF, i).model_dump() for i in ids)
    for x, i in ((a, ids[0]), (b, ids[1])):
        assert x["scenario_id"] == i
        x.pop("scenario_id")
        x["queue"] = [{**f, "alert_id": f["alert_id"].replace(i, "ID")} for f in x["queue"]]
        x["safety"] = []
    assert a == b
    assert "secret" not in str(a) and "secret" not in str(b)  # truth never reaches the assessment
    assess._case.cache_clear()


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
        (lambda: assess.replay_case("F1-500"), "UNKNOWN_CASE"),
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


MORNINGSIDE_A = "bloomington_morningside_2024_04_11:A"


def test_replay_morningside_a_warns_before_failure_with_three_repair_rows():
    r = assess.replay_case(MORNINGSIDE_A)
    assert r.first_investigate_at < r.failure_at and r.lead_time_h > 0
    assert [s.label for s in r.outcome.sensitivity] == ["repair 24 h", "repair 48 h", "repair 96 h"]
    assert r.outcome.no_warning_gal > 0 and r.truth["transforms"]


def test_replay_fishers_a_goes_offline_fast_and_flags_stand_in_history():
    r = assess.replay_case("fishers_bowline_2009_01_20:A")
    assert r.source_offline_after_min <= 15
    assert [s.label for s in r.outcome.sensitivity] == [
        "if staff would otherwise find out at 60 min",
        "if staff would otherwise find out at 180 min",
        "if staff would otherwise find out at 360 min",
    ]
    assert r.outcome.with_dragonfly_gal < r.outcome.no_warning_gal
    assert any("stand-in history" in a for a in r.outcome.assumptions)


def test_scenario_assessment_and_evidence_use_the_case_stream():
    t = datetime(2024, 4, 10, tzinfo=timezone.utc)
    a = assess.assess_station("44371", t, MORNINGSIDE_A)
    assert (
        a.origin == "SIMULATED_INCIDENT"
        and a.provenance.scenario_hash
        and a.queue[0].alert_id.startswith(MORNINGSIDE_A)
    )
    assert assess.get_evidence(a.queue[0].alert_id, t).origin == "SIMULATED_INCIDENT"


def test_scenario_markers_only_count_findings_opened_in_the_scored_window():
    from backend import api

    for case in ("fishers_bowline_2009_01_20:A", "bloomington_morningside_2024_04_11:A"):
        r = assess.replay_case(case)
        start = r.failure_at - timedelta(days=30)
        assert api.stations(case).stations[0].as_of_min == start
        days = {d.day: d.station_status for d in r.timeline}
        for marker in (r.first_watch_at, r.first_investigate_at):
            if marker is not None:
                assert marker > start
                opened = marker.date() - timedelta(days=1)
                assert days[opened - timedelta(days=1)] != days[opened]  # a new finding, not one carried in


def test_onset_variants_report_their_onset_minute():
    assert assess.replay_case("fishers_bowline_2009_01_20:B").high_level_after_min is not None
    assert assess.replay_case("fishers_bowline_2009_01_20:A").source_offline_after_min is not None
