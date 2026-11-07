"""Locked benchmark scenarios: parse, required sections present, rain file hash pinned."""

import hashlib
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = sorted((ROOT / "fixtures" / "scenarios").glob("*.toml"))
OUTCOMES = {"PREDICTABLE_DAYS_AHEAD", "DETECTABLE_AT_ONSET", "NOT_DETECTABLE"}
VARIANT_FIELDS = [
    "mechanism",
    "precursor_type",
    "precursor_onset_days_before",
    "capacity_lost_pct_at_failure",
    "precursor_shape",
    "failure_timestamp_utc",
    "backup_failed",
    "expected_detector_outcome",
]


def walk_fields(node):
    if isinstance(node, dict):
        if "status" in node and "value" in node:
            yield node
        for v in node.values():
            yield from walk_fields(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_fields(v)


def test_two_scenarios_exist():
    assert len(SCENARIOS) >= 2


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_scenario(path):
    s = tomllib.loads(path.read_text())
    assert s["id"] == path.stem and s["locked"] is True and s["version"]
    for section in [
        "record",
        "mechanism",
        "variants",
        "conditions",
        "station_standin",
        "outcome",
        "expected",
    ]:
        assert section in s, section
    assert s["mechanism"]["primary_variant"] in s["variants"]
    for name, v in s["variants"].items():
        for f in VARIANT_FIELDS:
            assert f in v, f"{name}.{f}"
        assert v["expected_detector_outcome"]["value"] in OUTCOMES
    for f in walk_fields(s):
        assert f["status"] in {"VERIFIED", "UNVERIFIED"}
        assert 0 <= f["confidence"] <= 100
    rain = ROOT / s["conditions"]["rain_file"]
    assert hashlib.sha256(rain.read_bytes()).hexdigest() == s["conditions"]["rain_file_sha256"]
    assert s["outcome"]["overflow_volume_tolerance_pct"] == 20
