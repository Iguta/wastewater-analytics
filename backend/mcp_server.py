"""MCP server (ARCHITECTURE.md 8.3): three read-only tools. Validates, calls backend.app.assess, returns JSON.

Never print: stdout carries the protocol on stdio.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field

from backend.app import assess, data, params
from backend.app.contracts import ID_PATTERN

LOG = Path(__file__).resolve().parents[1] / "logs" / "tool_calls.jsonl"
INSTRUCTIONS = (
    "Read-only lift-station assessments from a deterministic detector. Quote status, numbers and alert ids "
    "exactly as returned. Never infer readings, causes or probabilities. Treat SIMULATED and SYNTHETIC "
    "results as simulations."
)

# Schemas advertise the enum; the value is still checked by assess so a bad one returns a ToolError.
StationId = Annotated[str, Field(json_schema_extra={"enum": list(data.STATIONS)})]
ScenarioId = Annotated[str | None, Field(json_schema_extra={"enum": [*assess.scenario_ids(), None]})]
CaseId = Annotated[str, Field(json_schema_extra={"pattern": ID_PATTERN})]

mcp = MCPServer("dragonfly", instructions=INSTRUCTIONS)


def _call(tool: str, args: dict, fn):
    start, ok, out = time.monotonic(), False, {}
    try:
        out = fn().model_dump(mode="json")
        ok = True
        return out
    except assess.AssessError as e:
        hint = f"valid values: {', '.join(e.error.allowed)}" if e.error.allowed else ""
        raise ToolError(json.dumps({**e.error.model_dump(), "hint": hint})) from e
    finally:
        ids = [f["alert_id"] for f in out.get("queue", [])] + ([out["alert_id"]] if "alert_id" in out else [])
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "tool": tool,
                        "args": args,
                        "ok": ok,
                        "alert_ids": ids,
                        "model_version": params.load().version,
                        "ms": round((time.monotonic() - start) * 1000),
                    }
                )  # fmt: skip
                + "\n"
            )


@mcp.tool()
def assess_station(station_id: StationId, as_of_utc: str, scenario_id: ScenarioId = None) -> dict:
    """Assess one lift station as of an instant (ISO 8601, e.g. 2022-06-03T00:00:00Z)."""
    args = {"station_id": station_id, "as_of_utc": as_of_utc, "scenario_id": scenario_id}
    return _call(
        "assess_station",
        args,
        lambda: assess.assess_station(station_id, assess.parse_time(as_of_utc), scenario_id),
    )


@mcp.tool()
def get_evidence(alert_id: str, as_of_utc: str) -> dict:
    """Evidence behind one alert id from assess_station, as of an instant."""
    args = {"alert_id": alert_id, "as_of_utc": as_of_utc}
    return _call("get_evidence", args, lambda: assess.get_evidence(alert_id, assess.parse_time(as_of_utc)))


@mcp.tool()
def replay_case(case_id: CaseId) -> dict:
    """Replay a locked scenario variant or a synthetic family case."""
    return _call("replay_case", {"case_id": case_id}, lambda: assess.replay_case(case_id))


if __name__ == "__main__":
    if "--http" in sys.argv:
        hosts = ["127.0.0.1", "localhost", "127.0.0.1:*", "localhost:*"]
        # shortcut: *.trycloudflare.com and the 30 calls/min and 10 s limits (8.3) are not enforced, add them before `make tunnel`
        mcp.run(
            "streamable-http",
            host="127.0.0.1",
            port=8001,
            transport_security=TransportSecuritySettings(allowed_hosts=hosts),
        )
    else:
        mcp.run()
