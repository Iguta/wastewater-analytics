"""REST API (ARCHITECTURE.md 8.2). Validates, calls backend.app.assess, returns models. One uvicorn worker."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import cache
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import agent
from backend.app import assess, data, evaluate, params, scenarios
from backend.app.contracts import (
    AskResult,
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
STATUS = {"NO_REPORT": 404}  # §8.2: only a missing report is 404; every other ToolError is 422
EXPERIMENTS = {"F2": "storm_test", "F5": "cut_power", "F6": "break_sensor", "F4": "one_bad_day"}
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
    source_hash, model_version = data.sha256_file(data.WESSEX / "manifest.json"), params.load().version
    if scenario_id:
        if not assess.known_case(scenario_id):
            raise assess.AssessError(
                "UNKNOWN_SCENARIO", f"unknown scenario {scenario_id!r}", assess.scenario_ids()
            )
        sd, _, meta = assess._case(scenario_id)
        info = StationInfo(
            station_id=sd.station_id, display_name=f"Wessex {sd.station_id}", pumps=sd.pumps, origin=meta["origin"],
            scenario_id=scenario_id, as_of_min=assess._utc(sd.events["ts"].min()), as_of_max=assess._utc(sd.events["ts"].max()),
            outage_windows=[],
        )  # fmt: skip
        return StationsResponse(stations=[info], source_hash=source_hash, model_version=model_version)
    outage = (datetime(2023, 8, 17, tzinfo=timezone.utc), datetime(2023, 8, 20, tzinfo=timezone.utc))
    infos = [
        StationInfo(
            station_id=s, display_name=f"Wessex {s}", pumps=data.load(s).pumps, origin="REAL_REPLAY",
            scenario_id=None, as_of_min=assess.REAL_MIN, as_of_max=assess.REAL_MAX, outage_windows=[outage],
        )
        for s in data.STATIONS
    ]  # fmt: skip
    return StationsResponse(stations=infos, source_hash=source_hash, model_version=model_version)


def _facts(table: dict) -> list[Fact]:
    return [
        Fact(label=k, value=str(f["value"]), status=f["status"], confidence=f["confidence"], source=f.get("source", f.get("note", "")), source_url=None)
        for k, f in table.items()
        if isinstance(f, dict) and "status" in f
    ]  # fmt: skip


@cache
def dev_cases() -> list[DevCase]:
    """5.6: the first dev seed of F2, F5 and F6, and the first F4 dev seed with loss >= 0.4."""
    cases = evaluate.make_cases("dev", {"F2": 1, "F5": 1, "F6": 1, "F4": 30})
    picked = [
        next(c for c in cases if c.family == f and (f != "F4" or c.spec["loss"] >= 0.4)) for f in EXPERIMENTS
    ]
    return [DevCase(case_id=c.case_id, experiment=EXPERIMENTS[c.family]) for c in picked]


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
    return ScenariosResponse(scenarios=cards, dev_cases=dev_cases())


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
async def ask(req: AskRequest) -> AskResult:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return JSONResponse({"error": "agent_offline"}, 503)
    try:
        return await agent.ask(req.question, req.model_dump(exclude={"question"}))
    except TimeoutError:
        return JSONResponse({"error": "timeout"}, 504)


if (ROOT / "frontend" / "dist").is_dir():  # last, so it never shadows /api
    app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True))
