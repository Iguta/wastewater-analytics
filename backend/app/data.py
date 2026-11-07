"""Load one station's committed Wessex fixtures (ARCHITECTURE.md §3.4, §8.1).

Naive timestamps are UTC as recorded. Scenario truth is never attached to StationData.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import quality

ROOT = Path(__file__).resolve().parents[2]
WESSEX = ROOT / "fixtures" / "wessex"
SCENARIOS = ROOT / "fixtures" / "scenarios"
STATIONS = ("44371", "45385", "45078")


class UnknownStation(KeyError):
    pass


class UnknownScenario(KeyError):
    pass


@dataclass
class StationData:
    station_id: str
    events: pd.DataFrame  # signal_id, pump_id, ts, state (0/1)
    level: pd.DataFrame  # signal_id, ts, value, units, in_range
    rain: pd.DataFrame  # ts_hour, mm (NaN = missing, never 0)
    pumps: list[str]
    source_hash: str  # sha256 of manifest.json
    scenario_id: str | None = None
    scenario_hash: str | None = None
    signal_ids: list[str] = field(default_factory=list)
    quality_counts: dict = field(default_factory=dict)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def scenario_station(scenario_id: str) -> tuple[str, str]:
    """Scenario id -> (Wessex stand-in station, sha256 of the scenario TOML)."""
    p = SCENARIOS / f"{scenario_id}.toml"
    if not p.exists():
        raise UnknownScenario(scenario_id)
    s = tomllib.loads(p.read_text())
    return s["station_standin"]["wessex_site"]["value"], sha256_file(p)


def load(station_id: str | None, scenario_id: str | None = None) -> StationData:
    scenario_hash = None
    if scenario_id is not None:
        standin, scenario_hash = scenario_station(scenario_id)
        station_id = station_id or standin
    if station_id not in STATIONS:
        raise UnknownStation(station_id)
    d = WESSEX / station_id
    counts: dict = {}
    events = quality.parse_events(pd.read_parquet(d / "runstop.parquet"), counts)
    level = quality.parse_level(pd.read_parquet(d / "level.parquet"), counts)
    rain = pd.read_parquet(d / "rain.parquet")
    rain["ts_hour"] = pd.to_datetime(rain["ts_hour"])
    rain["mm"] = pd.to_numeric(rain["mm"], errors="coerce")
    counts["RAIN_GAP"] = int(rain["mm"].isna().sum())
    return StationData(
        station_id=station_id,
        events=events,
        level=level,
        rain=rain,
        pumps=sorted(events["pump_id"].unique()),
        source_hash=sha256_file(WESSEX / "manifest.json"),
        scenario_id=scenario_id,
        scenario_hash=scenario_hash,
        signal_ids=sorted(set(events["signal_id"]) | set(level["signal_id"])),
        quality_counts=counts,
    )
