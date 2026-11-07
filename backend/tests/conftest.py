"""Test setup that works from the repo root, where pytest does not read backend/pyproject.toml."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # so `backend.app` imports resolve


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.timeout(60))
