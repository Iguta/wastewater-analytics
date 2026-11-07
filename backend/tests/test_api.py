import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import api
from backend.app.contracts import (
    AskResult,
    Grounding,
    ScenariosResponse,
    StationAssessment,
    StationsResponse,
    ToolError,
)

UI = Path(__file__).resolve().parents[2] / "fixtures" / "ui"
client = TestClient(api.app)
AS_OF = "2022-06-03T00:00:00Z"


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_stations_and_scenarios():
    assert len(StationsResponse.model_validate(client.get("/api/stations").json()).stations) == 3
    s = ScenariosResponse.model_validate(client.get("/api/scenarios").json())
    assert {c.id for c in s.scenarios} == {"bloomington_morningside_2024_04_11", "fishers_bowline_2009_01_20"}
    assert [d.experiment for d in s.dev_cases] == ["storm_test", "cut_power", "break_sensor", "one_bad_day"]


def test_assess_then_evidence_then_timeline():
    r = client.get("/api/assess", params={"station_id": "44371", "as_of_utc": AS_OF})
    a = StationAssessment.model_validate(r.json())
    assert a.status in ("WATCH", "INVESTIGATE")
    e = client.get("/api/evidence", params={"alert_id": a.queue[0].alert_id, "as_of_utc": AS_OF})
    assert e.status_code == 200 and e.json()["finding"]["alert_id"] == a.queue[0].alert_id
    t = client.get(
        "/api/timeline", params={"station_id": "44371", "start": "2022-06-01T00:00:00Z", "end": AS_OF}
    )
    assert t.status_code == 200 and t.json()


@pytest.mark.parametrize(
    "path, params, status, code",
    [
        ("/api/assess", {"station_id": "1", "as_of_utc": AS_OF}, 422, "UNKNOWN_STATION"),
        ("/api/assess", {"station_id": "44371"}, 422, "BAD_TIMESTAMP"),
        ("/api/assess", {"station_id": "44371", "as_of_utc": "2022-06-03"}, 422, "BAD_TIMESTAMP"),
        ("/api/replay", {"case_id": "F1-500"}, 422, "UNKNOWN_CASE"),
        ("/api/replay", {"case_id": "bad"}, 422, "UNKNOWN_CASE"),
    ],
)
def test_errors_are_tool_errors(path, params, status, code):
    r = client.get(path, params=params)
    assert r.status_code == status and ToolError.model_validate(r.json()).code == code


def test_evaluation_report_or_no_report(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "ROOT", tmp_path)
    r = client.get("/api/evaluation")
    assert r.status_code == 404 and r.json()["code"] == "NO_REPORT"
    (tmp_path / "reports").mkdir()
    shutil.copy(UI / "evaluation.json", tmp_path / "reports" / "evaluation.json")
    assert client.get("/api/evaluation").json()["model_version"] == "v1.0"


def test_ask_offline_without_key_and_rejects_bad_questions(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.post("/api/ask", json={"question": "why?"}).status_code == 503
    for q in ("", "x" * 2001):
        r = client.post("/api/ask", json={"question": q})
        assert r.status_code == 422 and r.json()["code"] == "BAD_QUESTION"


def test_ask_returns_agent_result_and_504_on_timeout(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    seen = {}

    async def fake(question, context, session_id=None):
        seen.update(question=question, context=context, session_id=session_id)
        return AskResult(
            answer_markdown="ok", withheld=False, tool_calls=[], grounding=Grounding(passed=True, unmatched_numbers=[], forbidden_phrases=[]),
            model="m", fallback_dropped=False,
        )  # fmt: skip

    monkeypatch.setattr(api.agent, "ask", fake)
    r = client.post("/api/ask", json={"question": "why?", "station_id": "44371", "session_id": "s1"})
    assert (
        AskResult.model_validate(r.json()).answer_markdown == "ok"
        and seen["context"]["station_id"] == "44371"
        and "session_id" not in seen["context"]
        and seen["session_id"] == "s1"
    )

    async def slow(question, context, session_id=None):
        raise TimeoutError

    monkeypatch.setattr(api.agent, "ask", slow)
    assert client.post("/api/ask", json={"question": "why?"}).status_code == 504


def test_ask_validates_inputs_and_maps_agent_failures(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    for body, code in (
        ({"station_id": "x"}, "UNKNOWN_STATION"),
        ({"scenario_id": "x"}, "UNKNOWN_SCENARIO"),
        ({"as_of_utc": "2022-06-03"}, "BAD_TIMESTAMP"),
    ):
        r = client.post("/api/ask", json={"question": "why?", **body})
        assert r.status_code == 422 and r.json()["code"] == code

    async def boom(question, context, session_id=None):
        raise ExceptionGroup("tg", [RuntimeError("x")])

    async def wrapped(question, context, session_id=None):
        raise ExceptionGroup("tg", [TimeoutError()])

    monkeypatch.setattr(api.agent, "ask", boom)
    r = client.post("/api/ask", json={"question": "why?"})
    assert r.status_code == 502 and r.json()["code"] == "AGENT_ERROR"
    monkeypatch.setattr(api.agent, "ask", wrapped)
    r = client.post("/api/ask", json={"question": "why?"})
    assert r.status_code == 504 and r.json()["code"] == "AGENT_TIMEOUT"


def test_feedback_is_logged_read_back_and_never_changes_assess(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "ROOT", tmp_path)
    params = {"station_id": "44371", "as_of_utc": AS_OF}
    before = client.get("/api/assess", params=params).json()
    alert_id = before["queue"][0]["alert_id"]
    fb = {
        "alert_id": alert_id,
        "verdict": "found_issue",
        "by": "op1",
        "note": "ragged impeller",
        "at_utc": AS_OF,
    }
    assert client.post("/api/feedback", json=fb).status_code == 200
    assert len((tmp_path / "logs" / "feedback.jsonl").read_text().splitlines()) == 1
    assert client.get("/api/feedback", params={"alert_id": alert_id}).json() == [fb]
    assert client.get("/api/assess", params=params).json() == before
    assert before["queue"][0]["priority_reason"].startswith("Rank 1 of ")


@pytest.mark.parametrize("bad", [{"verdict": "maybe"}, {"note": "x" * 501}, {"alert_id": "nope"}])
def test_feedback_rejects_bad_input(monkeypatch, tmp_path, bad):
    monkeypatch.setattr(api, "ROOT", tmp_path)
    fb = {
        "alert_id": "REAL:44371:P2:CAPACITY_DROP:2022-09-02",
        "verdict": "checked_ok",
        "by": "op1",
        "note": "",
        "at_utc": AS_OF,
    }
    r = client.post("/api/feedback", json={**fb, **bad})
    assert r.status_code == 422 and r.json()["code"] in ("BAD_FEEDBACK", "UNKNOWN_ALERT")
    assert not (tmp_path / "logs").exists()
