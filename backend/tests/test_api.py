import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import api
from backend.app.contracts import ScenariosResponse, StationAssessment, StationsResponse, ToolError

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
        ("/api/assess", {"station_id": "1", "as_of_utc": AS_OF}, 404, "UNKNOWN_STATION"),
        ("/api/assess", {"station_id": "44371"}, 422, "BAD_TIMESTAMP"),
        ("/api/assess", {"station_id": "44371", "as_of_utc": "2022-06-03"}, 422, "BAD_TIMESTAMP"),
        ("/api/replay", {"case_id": "F1-1003"}, 501, "NOT_AVAILABLE"),
        ("/api/replay", {"case_id": "bad"}, 404, "UNKNOWN_CASE"),
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


def test_ask_is_offline_and_rejects_empty_question():
    assert client.post("/api/ask", json={"question": "why?"}).status_code == 503
    r = client.post("/api/ask", json={"question": ""})
    assert r.status_code == 422 and r.json()["code"] == "BAD_QUESTION"
