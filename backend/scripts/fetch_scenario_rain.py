"""Fetch hourly Open-Meteo historical rainfall for each benchmark scenario.

Writes fixtures/scenarios/rain/<scenario_id>.csv (UTC, inches)
and prints the SHA-256 of each file so the scenario TOML can pin it.

Usage: python backend/scripts/fetch_scenario_rain.py
"""

import csv
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
OUT_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "scenarios" / "rain"

# Window: 30 days before the failure date to 2 days after.
SCENARIOS = {
    "bloomington_morningside_2024_04_11": {
        "lat": 39.1673,
        "lon": -86.4720,
        "start": "2024-03-12",
        "end": "2024-04-13",
    },
    "fishers_bowline_2009_01_20": {
        "lat": 39.9505,
        "lon": -85.8911,
        "start": "2008-12-21",
        "end": "2009-01-22",
    },
}


def fetch(sid: str, s: dict) -> Path:
    q = urllib.parse.urlencode(
        {
            "latitude": s["lat"],
            "longitude": s["lon"],
            "start_date": s["start"],
            "end_date": s["end"],
            "hourly": "precipitation",
            "precipitation_unit": "inch",
            "timezone": "GMT",
        }
    )
    url = f"{ARCHIVE}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "wastewater-analytics"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    hourly = data["hourly"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{sid}.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_utc", "precipitation_in"])
        for t, p in zip(hourly["time"], hourly["precipitation"]):
            w.writerow([t, "" if p is None else p])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(
        f"{sid}: {len(hourly['time'])} rows, grid {data['latitude']},{data['longitude']}, "
        f"tz {data['timezone']} ({data['timezone_abbreviation']}), sha256 {digest}"
    )
    print(f"  source: {url}")
    return path


if __name__ == "__main__":
    for sid, s in SCENARIOS.items():
        fetch(sid, s)
