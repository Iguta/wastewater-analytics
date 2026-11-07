"""Contract tests: every UI sample validates and round-trips; extra fields are rejected."""

import json
import re
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.app import contracts as c

UI = Path(__file__).resolve().parents[2] / "fixtures" / "ui"
SAMPLES = {
    "stations": c.StationsResponse,
    "scenarios": c.ScenariosResponse,
    "assess": c.StationAssessment,
    "evidence": c.Evidence,
    "timeline": list[c.TimelineDay],
    "replay": c.ReplayResult,
    "ask": c.AskResult,
}


@pytest.mark.parametrize("name", SAMPLES)
def test_sample_round_trips(name):
    adapter = TypeAdapter(SAMPLES[name])
    raw = json.loads((UI / f"{name}.json").read_text())
    assert json.loads(adapter.dump_json(adapter.validate_python(raw))) == raw


def test_evaluation_sample():
    # No section 7 model exists for evaluation.json, so check only what the UI relies on.
    assert "model_version" in json.loads((UI / "evaluation.json").read_text())


@pytest.mark.parametrize("case_id", ["bloomington_morningside_2024_04_11:A", "F1-1003"])
def test_id_pattern_accepts(case_id):
    assert re.match(c.ID_PATTERN, case_id)


def test_tool_error_round_trips_and_rejects_unknown_code():
    e = c.ToolError(code="NO_REPORT", message="run make eval", allowed=[])
    assert c.ToolError.model_validate_json(e.model_dump_json()) == e
    with pytest.raises(ValidationError):
        c.ToolError(code="NOPE", message="x", allowed=[])


def test_extra_fields_rejected():
    raw = json.loads((UI / "assess.json").read_text())
    with pytest.raises(ValidationError):
        c.StationAssessment.model_validate({**raw, "surprise": 1})


def test_naive_datetime_rejected_and_offset_normalised_to_z():
    base = {"ts": "2022-09-02T00:00:00", "value": 1.0, "units": "m"}
    with pytest.raises(ValidationError):
        c.LevelPoint.model_validate(base)
    p = c.LevelPoint.model_validate({**base, "ts": "2022-09-02T02:00:00+02:00"})
    assert p.model_dump_json().count("2022-09-02T00:00:00Z") == 1
