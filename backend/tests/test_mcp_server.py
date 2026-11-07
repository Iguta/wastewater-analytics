import json

import anyio
from mcp import Client

from backend import mcp_server
from backend.app.contracts import StationAssessment


async def _exercise():
    async with Client(mcp_server.mcp) as c:
        tools = (await c.list_tools()).tools
        assert sorted(t.name for t in tools) == ["assess_station", "get_evidence", "replay_case"]
        r = await c.call_tool("assess_station", {"station_id": "44371", "as_of_utc": "2022-06-03T00:00:00Z"})
        assert not r.is_error
        StationAssessment.model_validate_json(r.content[0].text)
        bad = await c.call_tool("assess_station", {"station_id": "1", "as_of_utc": "2022-06-03T00:00:00Z"})
        assert bad.is_error and "UNKNOWN_STATION" in bad.content[0].text


def test_three_tools_and_a_valid_assessment(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "LOG", tmp_path / "tool_calls.jsonl")
    anyio.run(_exercise)
    log = [json.loads(line) for line in (tmp_path / "tool_calls.jsonl").read_text().splitlines()]
    assert [e["ok"] for e in log] == [True, False] and log[0]["alert_ids"]


def test_replay_case_hides_ground_truth(tmp_path, monkeypatch):
    class Fake:
        def model_dump(self, mode):
            return {"case_id": "F1-0", "truth": {"loss_24h": 0.4}, "timeline": [1, 2]}

    monkeypatch.setattr(mcp_server, "LOG", tmp_path / "t.jsonl")
    monkeypatch.setattr(mcp_server.assess, "replay_case", lambda _: Fake())
    out = mcp_server.replay_case("F1-0")
    assert "truth" not in out and "timeline" not in out


def test_get_evidence_is_small_enough_for_a_model(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "LOG", tmp_path / "t.jsonl")
    from backend.app import assess

    t = assess.parse_time("2022-06-03T00:00:00Z")
    alert = assess.assess_station("44371", t).queue[0].alert_id
    out = mcp_server.get_evidence(alert, "2022-06-03T00:00:00Z")
    assert "level" not in out and "raw_events" not in out and len(out["trace"]) <= 14
    assert len(json.dumps(out, indent=2)) < 30_000
