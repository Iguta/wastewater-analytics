"""REST API (ARCHITECTURE.md 8.2). Validates, calls backend.app.assess, returns models. One uvicorn worker."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.app import assess, data, params, scenarios
from backend.app.contracts import (
    DevCase,
    EvaluationReport,
    Fact,
    ScenarioCard,
    ScenariosResponse,
    StationInfo,
    StationsResponse,
    ToolError,
    VariantCard,
)

ROOT = Path(__file__).resolve().parents[1]
STATUS = {"UNKNOWN": 404, "NO_REPORT": 404, "NOT_AVAILABLE": 501}  # by code prefix; anything else is 422
# The Lab's fixed dev cases (5.6). F4's seed is a placeholder until David picks the first one with loss >= 0.4.
DEV_CASES = [
    DevCase(case_id="F2-0", experiment="storm_test"),
    DevCase(case_id="F5-0", experiment="cut_power"),
    DevCase(case_id="F6-0", experiment="break_sensor"),
    DevCase(case_id="F4-0", experiment="one_bad_day"),
]
# Which query parameter a validation failure names -> its error code.
PARAM_CODE = {
    "station_id": "UNKNOWN_STATION",
    "scenario_id": "UNKNOWN_SCENARIO",
    "alert_id": "UNKNOWN_ALERT",
    "case_id": "UNKNOWN_CASE",
    "question": "BAD_QUESTION",
}

app = FastAPI(title="Dragonfly")


def tool_error(code: str, message: str, allowed: list[str] | None = None) -> JSONResponse:
    status = next((s for prefix, s in STATUS.items() if code.startswith(prefix)), 422)
    return JSONResponse(ToolError(code=code, message=message, allowed=allowed or []).model_dump(), status)


@app.exception_handler(assess.AssessError)
async def _assess_error(_: Request, e: assess.AssessError):
    return tool_error(e.error.code, e.error.message, e.error.allowed)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, e: RequestValidationError):
    first = e.errors()[0]
    code = next((PARAM_CODE.get(str(x), "BAD_TIMESTAMP") for x in first["loc"][1:2]), "BAD_TIMESTAMP")
    return tool_error(code, f"{'.'.join(map(str, first['loc'][1:]))}: {first['msg']}")


@app.get("/api/health")
def health():
    if not (data.WESSEX / "manifest.json").exists():
        return JSONResponse({"status": "manifest_missing"}, 503)
    return {
        "status": "ok",
        "model_version": params.load().version,
        "source_hash": data.sha256_file(data.WESSEX / "manifest.json"),
        "code_version": assess.code_version(),
    }


@app.get("/api/stations")
def stations(scenario_id: str | None = None) -> StationsResponse:
    if scenario_id:
        assess.check("44371", scenario_id, assess.REAL_MIN)  # raises: scenarios are not available yet
    outage = (datetime(2023, 8, 17, tzinfo=timezone.utc), datetime(2023, 8, 20, tzinfo=timezone.utc))
    infos = [
        StationInfo(
            station_id=s, display_name=f"Station {s}", pumps=data.load(s).pumps, origin="REAL_REPLAY",
            scenario_id=None, as_of_min=assess.REAL_MIN, as_of_max=assess.REAL_MAX, outage_windows=[outage],
        )
        for s in data.STATIONS
    ]  # fmt: skip
    return StationsResponse(
        stations=infos,
        source_hash=data.sha256_file(data.WESSEX / "manifest.json"),
        model_version=params.load().version,
    )


def _facts(table: dict) -> list[Fact]:
    return [
        Fact(label=k, value=str(f["value"]), status=f["status"], confidence=f["confidence"], source=f.get("source", f.get("note", "")), source_url=None)
        for k, f in table.items()
        if isinstance(f, dict) and "status" in f
    ]  # fmt: skip


@app.get("/api/scenarios")
def scenario_list() -> ScenariosResponse:
    cards = []
    for path in sorted(data.SCENARIOS.glob("*.toml")):
        s, sha = scenarios.load(path.stem)
        variants = [
            VariantCard(
                variant=v, scenario_id=f"{path.stem}:{v}", name=var["name"], confidence=var["mechanism"]["confidence"],
                reason=var["mechanism"]["value"], detectability=var["expected_detector_outcome"]["value"],
                failure_at=scenarios.v(var["failure_timestamp_utc"]),
            )
            for v, var in s["variants"].items()
        ]  # fmt: skip
        cards.append(
            ScenarioCard(
                id=s["id"], title=s["title"], version=s["version"], scenario_hash=sha,
                facts=_facts(s["record"]), outcome_facts=_facts(s["outcome"]), variants=variants,
            )
        )  # fmt: skip
    return ScenariosResponse(scenarios=cards, dev_cases=DEV_CASES)


@app.get("/api/assess")
def assess_route(station_id: str, as_of_utc: str, scenario_id: str | None = None):
    return assess.assess_station(station_id, assess.parse_time(as_of_utc), scenario_id)


@app.get("/api/evidence")
def evidence(alert_id: str, as_of_utc: str):
    return assess.get_evidence(alert_id, assess.parse_time(as_of_utc))


@app.get("/api/timeline")
def timeline(station_id: str, start: str, end: str, scenario_id: str | None = None):
    return assess.timeline(station_id, scenario_id, assess.parse_time(start), assess.parse_time(end))


@app.get("/api/replay")
def replay(case_id: str):
    return assess.replay_case(case_id)


@app.get("/api/evaluation")
def evaluation() -> EvaluationReport:
    path = ROOT / "reports" / "evaluation.json"
    if not path.exists():
        raise assess.AssessError(
            "NO_REPORT", "reports/evaluation.json does not exist; run the evaluation first"
        )
    return EvaluationReport.model_validate_json(path.read_text())


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    station_id: str | None = None
    as_of_utc: str | None = None
    scenario_id: str | None = None


@app.post("/api/ask")
def ask(_: AskRequest):
    return JSONResponse({"error": "agent_offline"}, 503)


if (ROOT / "frontend" / "dist").is_dir():  # last, so it never shadows /api
    app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True))
