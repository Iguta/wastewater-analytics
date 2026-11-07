"""Export the three model stations from the raw Wessex files into small committed fixtures.

ARCHITECTURE.md §3.4. Reads raw files from $WESSEX_DIR (never committed) and writes
fixtures/wessex/<station>/{runstop,level,rain}.parquet (zstd, raw rows unmodified apart from
column naming/typing) plus fixtures/wessex/manifest.json.

Usage: WESSEX_DIR=~/wastewater-data/wessex python backend/scripts/export_fixtures.py
"""

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import pandas as pd

STATIONS = ["44371", "45385", "45078"]
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "fixtures" / "wessex"
FILES = {
    "runstop": "sps-run-stop-data.csv",
    "level": "sps-wet-well-level-data.zip",
    "rain": "sps-local-rainfall-data.csv",
    "key": "rising-main-diameter-and-key-to-telemetry-signals.csv",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def station_of(signal: pd.Series) -> pd.Series:
    return signal.str.split("_", n=1).str[0]


def export_runstop(src: Path) -> dict[str, int]:
    df = pd.read_csv(src, dtype=str)
    df.columns = ["signal_id", "ts", "value"]
    df = df[station_of(df.signal_id).isin(STATIONS)]
    counts = {}
    for st, g in df.groupby(station_of(df.signal_id)):
        out = pd.DataFrame({"signal_id": g.signal_id, "ts": g.ts, "value": g.value})
        write(out, st, "runstop")
        counts[st] = len(out)
    return counts


def export_level(src: Path) -> dict[str, int]:
    parts = []
    with zipfile.ZipFile(src) as z:
        name = z.namelist()[0]
        with z.open(name) as raw:
            reader = pd.read_csv(io.TextIOWrapper(raw), dtype=str, chunksize=2_000_000)
            for chunk in reader:
                chunk.columns = ["signal_id", "ts", "value", "units"]
                parts.append(chunk[station_of(chunk.signal_id).isin(STATIONS)])
    df = pd.concat(parts)
    df["value"] = df["value"].str.strip()
    counts = {}
    for st, g in df.groupby(station_of(df.signal_id)):
        write(g.reset_index(drop=True), st, "level")
        counts[st] = len(g)
    return counts


def export_rain(src: Path) -> dict[str, int]:
    df = pd.read_csv(src, dtype=str)
    df.columns = ["site", "date", "hour", "mm"]
    df = df[df.site.str.strip().isin(STATIONS)]
    counts = {}
    for st, g in df.groupby(df.site.str.strip()):
        ts_hour = pd.to_datetime(g.date, format="%d/%m/%Y") + pd.to_timedelta(g.hour.astype(int), unit="h")
        out = pd.DataFrame({"ts_hour": ts_hour.dt.strftime("%Y-%m-%d %H:%M:%S"), "mm": g.mm.str.strip()})
        write(out.reset_index(drop=True), st, "rain")
        counts[st] = len(out)
    return counts


def write(df: pd.DataFrame, station: str, kind: str) -> None:
    d = OUT / station
    d.mkdir(parents=True, exist_ok=True)
    df.reset_index(drop=True).to_parquet(d / f"{kind}.parquet", compression="zstd", index=False)


def main() -> None:
    src = Path(os.environ["WESSEX_DIR"]).expanduser()
    paths = {k: src / v for k, v in FILES.items()}
    rows = {
        "runstop": export_runstop(paths["runstop"]),
        "level": export_level(paths["level"]),
        "rain": export_rain(paths["rain"]),
    }
    key = pd.read_csv(paths["key"], dtype=str)
    key = key[key.iloc[:, 0].str.strip().isin(STATIONS)]
    OUT.mkdir(parents=True, exist_ok=True)
    key.to_csv(OUT / "signal_key.csv", index=False)
    manifest = {
        "stations": STATIONS,
        "filter": "signal_id prefix / Marketplace Site ID in stations; rows otherwise unmodified",
        "sources": {FILES[k]: sha256(p) for k, p in paths.items()},
        "rows_exported": rows,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
