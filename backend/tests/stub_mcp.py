"""Stub Dragonfly MCP server with fixed output, for the Agent SDK loop test."""

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("dragonfly")
OUT = {
    "station_id": "44371",
    "status": "INVESTIGATE",
    "pumps": [
        {"pump_id": "P1", "status": "INVESTIGATE", "capacity_change_pct": -31.2},
        {"pump_id": "P2", "status": "NORMAL"},
    ],
    "queue": [{"alert_id": "REAL:44371:P1:CAPACITY_DROP:2022-06-01"}],
}


@mcp.tool()
def assess_station(station_id: str, as_of_utc: str, scenario_id: str | None = None) -> dict:
    return OUT


@mcp.tool()
def get_evidence(alert_id: str, as_of_utc: str) -> dict:
    return {"alert_id": alert_id}


@mcp.tool()
def replay_case(case_id: str) -> dict:
    return {"case_id": case_id}


if __name__ == "__main__":
    mcp.run()
