"""Load frozen detector parameters from params.toml (§4.14)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

PATH = Path(__file__).with_name("params.toml")


@dataclass(frozen=True)
class Params:
    version: str
    k: float
    U: float
    h_w: float
    h_i: float
    W: int
    G: int
    min_valid_cycles: int = 20
    min_baseline_days: int = 30
    reopen_days: int = 7
    S_max: float = 12.0
    sibling_mode: str = "shared_drop"
    persistence: bool = True
    inhibition: bool = True
    quality_gate: bool = True

    def with_(self, **kw) -> Params:
        return replace(self, **kw)


def load(path: Path = PATH) -> Params:
    return Params(**tomllib.loads(path.read_text()))
