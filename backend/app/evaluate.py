"""Dev/test evaluation over the synthetic families F1-F7 and the real replay (ARCHITECTURE.md §5.6, §6).

`python -m backend.app.evaluate dev` writes reports/dev/summary.json (§11.6 keys) and reports/dev/cases.csv.
Daily feature tables are param-independent, so they are built once per case and cached in memory for tuning.
The test tier is scored only at freeze: `evaluate test` refuses to run without FREEZE=1.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, detect, features, inject, params

ROOT = Path(__file__).resolve().parents[2]
WINDOW_DAYS = 120
LOOKBACK_DAYS = 120  # baseline history kept before the window (W + G + warm-up margin)
TIERS = {"dev": (2022, 0), "test": (2023, 1000)}
FAMILIES = {"F1": 200, "F2": 30, "F3": 30, "F4": 30, "F5": 30, "F6": 30, "F7": 30}
REAL_OUTAGE = (pd.Timestamp("2023-08-17"), pd.Timestamp("2023-08-21"))


@cache
def station(st: str) -> data.StationData:
    return data.load(st)


@cache
def real_table(st: str, end: str) -> pd.DataFrame:
    s = station(st)
    return features.daily_table(s.events, s.level, s.rain, end, st)


def proxy_windows(st: str) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """§5.7 episodes (busy pump 0 runs >= 2 days while a sibling runs >= 10) at one station, for rejection."""
    t = real_table(st, "2024-01-01")
    r = detect.run(t, params.load())
    out = []
    for _p, g in r.groupby("pump_id"):
        g = g.sort_values("day")
        sib = r[r.pump_id != _p].groupby("day")["runs"].max().reindex(g.day).to_numpy()
        hit = (g.base_runs_median.to_numpy() >= 10) & (g.runs.to_numpy() == 0) & (sib >= 10)
        blk = np.cumsum(~hit)
        for b in np.unique(blk[hit]):
            days = g.day.to_numpy()[hit & (blk == b)]
            if len(days) >= 2:
                out.append((pd.Timestamp(days[0]), pd.Timestamp(days[-1])))
    return out


@dataclass
class Case:
    case_id: str
    family: str
    station: str
    start: pd.Timestamp  # first scored day
    end: pd.Timestamp  # exclusive
    spec: dict


def _window(rng, year: int, st: str, center=None) -> tuple[pd.Timestamp, pd.Timestamp, int]:
    """120-day scored window with W + G (74) days of real history before it. Windows within 14 days of a
    proxy episode or the real 2023-08 outage are redrawn; where none is clean (45385 2022 rotates pumps every
    6-10 weeks) the least-overlapping draw is used and its overlap count is recorded on the case."""
    lo = max(pd.Timestamp(f"{year}-01-01"), pd.Timestamp("2022-03-16"))
    hi = pd.Timestamp(f"{year + 1}-01-01") - pd.Timedelta(days=WINDOW_DAYS)
    bad = proxy_windows(st) + [REAL_OUTAGE]
    best = None
    for _ in range(200):
        if center is not None:
            s = min(max((center - pd.Timedelta(days=WINDOW_DAYS // 2)).floor("D"), lo), hi)
        else:
            s = lo + pd.Timedelta(days=int(rng.integers(0, max(1, (hi - lo).days))))
        e = s + pd.Timedelta(days=WINDOW_DAYS)
        k = sum(not (e < a - pd.Timedelta(days=14) or s > b + pd.Timedelta(days=14)) for a, b in bad)
        if best is None or k < best[2]:
            best = (s, e, k)
        if k == 0:
            break
        center = None
    return best


def make_cases(tier: str, families=FAMILIES) -> list[Case]:
    year, base = TIERS[tier]
    cases = []
    for fam, n in families.items():
        for i in range(n):
            seed = base + i
            rng = np.random.default_rng([int(fam[1]), seed])
            st = str(rng.choice(data.STATIONS))
            pumps = station(st).pumps
            spec: dict = {}
            center = None
            if fam == "F2":
                rain = station(st).rain.set_index("ts_hour")["mm"].resample("D").sum(min_count=20)
                wet = rain[rain.index.year == year].nlargest(30).index
                center = wet[i % len(wet)]
                spec["wet_day"] = center
            s, e, overlap = _window(rng, year, st, center)

            def day(lo, hi, s=s, rng=rng):
                return s + pd.Timedelta(days=float(rng.uniform(lo, hi)))

            if fam == "F1":
                failure = day(WINDOW_DAYS - 30, WINDOW_DAYS - 1).floor("h")
                ramp = float(rng.uniform(3, 30))
                spec = {
                    "pump": str(rng.choice(pumps)),
                    "failure": failure,
                    "onset": failure - pd.Timedelta(days=ramp + 1),
                    "loss_24h": float(rng.uniform(0.10, 0.50)),
                    "shape": "linear" if rng.random() < 0.5 else "accelerating",
                    "ramp_days": ramp,
                }
            elif fam == "F3":
                spec = {
                    "pump": str(rng.choice(pumps)),
                    "onset": day(20, 80).floor("D"),
                    "days": 30,
                    "share": float(rng.uniform(0.7, 0.9)),
                }
            elif fam == "F4":
                spec = {
                    "pump": str(rng.choice(pumps)),
                    "day": day(20, WINDOW_DAYS - 10).floor("D"),
                    "loss": float(rng.uniform(0.3, 0.5)),
                }
            elif fam == "F5":
                spec = {"start": day(20, WINDOW_DAYS - 10).floor("min"), "hours": float(rng.uniform(2, 12))}
            elif fam == "F6":
                spec = {
                    "kind": inject.SENSOR_KINDS[seed % len(inject.SENSOR_KINDS)],
                    "start": day(20, WINDOW_DAYS - 10).floor("min"),
                }
            elif fam == "F7":
                spec = {"onset": day(20, 80).floor("D"), "factor": float(rng.uniform(0.75, 0.85))}
            spec["proxy_overlap"] = overlap
            cases.append(Case(f"{fam}-{seed}", fam, st, s, e, spec))
    return cases


def _clip(sd: data.StationData, c: Case) -> data.StationData:
    lo = c.start - pd.Timedelta(days=LOOKBACK_DAYS)
    hi = c.end + pd.Timedelta(days=3)
    return data.StationData(
        **{
            **sd.__dict__,
            "events": sd.events[sd.events.ts.between(lo, hi)],
            "level": sd.level[sd.level.ts.between(lo, hi)],
            "rain": sd.rain[sd.rain.ts_hour.between(lo, hi)],
        }
    )


def build(c: Case) -> dict:
    """Inject the fault and build the param-independent daily table (plus realtime probes for F5/F6)."""
    sd = _clip(station(c.station), c)
    rng = np.random.default_rng([int(c.family[1]), int(c.case_id.split("-")[1]), 7])
    sp, truth = c.spec, {}
    if c.family == "F1":
        sd, truth = inject.capacity_loss(
            sd, sp["pump"], sp["onset"], sp["failure"], sp["loss_24h"], sp["shape"]
        )
    elif c.family == "F3":
        sd, truth = inject.duty_swap(sd, sp["pump"], sp["onset"], sp["days"], sp["share"], rng)
    elif c.family == "F4":
        sd, truth = inject.transient(sd, sp["pump"], sp["day"], sp["loss"])
    elif c.family == "F5":
        sd, truth = inject.outage(sd, sp["start"], sp["hours"])
    elif c.family == "F6":
        sd, truth = inject.sensor_fault(sd, sp["kind"], sp["start"], rng)
    elif c.family == "F7":
        sd, truth = inject.station_shift(sd, sp["onset"], sp["factor"])
    counts: dict = {}
    t = features.daily_table(sd.events, sd.level, sd.rain, c.end, c.station, counts)
    out = {"table": t, "truth": truth, "counts": counts}
    P = params.load()
    if c.family == "F5":
        mins = None
        for m in range(1, 31):
            f = detect.realtime(sd.events, sd.level, sp["start"] + pd.Timedelta(minutes=m), P)
            if any(x["type"] == "SOURCE_SILENT" for x in f):
                mins = m
                break
        out["minutes_to_offline"] = mins
    if c.family == "F6" and sp["kind"] in ("flatline", "dropout", "negative_spikes"):
        probe = {"flatline": 11 * 60, "dropout": 3 * 60, "negative_spikes": 30}[sp["kind"]]
        f = detect.realtime(sd.events, sd.level, sp["start"] + pd.Timedelta(minutes=probe), P)
        out["realtime_flags"] = sorted({fl for x in f if x["type"] == "SENSOR_FAULT" for fl in x["flags"]})
    if c.family in ("F1", "F2", "F3", "F4", "F7") or (
        c.family == "F6" and sp["kind"] in ("duplicate_rows", "repeated_starts")
    ):  # the same window without the fault: separates injected escalations from real background incidents
        clean = _clip(station(c.station), c)
        out["clean_table"] = features.daily_table(clean.events, clean.level, clean.rain, c.end, c.station)
    return out


REQUIRED_F6 = {
    "flatline": "LEVEL_FLATLINE",
    "dropout": "LEVEL_GAP",
    "negative_spikes": "LEVEL_OUT_OF_RANGE",
    "duplicate_rows": "DUPLICATE_ROW",
    "repeated_starts": "REPEATED_START",
}


def score(c: Case, b: dict, P: params.Params, background: set | None = None) -> dict:
    """Score one case. `background` = (pump, day) INVESTIGATE set of the un-injected data; when None it is
    computed from the case's own clean window (exact), the tuner passes a whole-station clean run (fast)."""
    r = detect.run(b["table"], P)
    win = r[(r.day >= c.start) & (r.day < c.end)]
    inv = win[win.status == "INVESTIGATE"]
    res = {"case_id": c.case_id, "family": c.family, "station": c.station}
    if background is None and "clean_table" in b:
        rc = detect.run(b["clean_table"], P)
        wc = rc[(rc.day >= c.start) & (rc.day < c.end) & (rc.status == "INVESTIGATE")]
        background = set(zip(wc.pump_id, wc.day))
    background = background or set()
    attributable = inv[
        np.array([(p_, d_) not in background for p_, d_ in zip(inv.pump_id, inv.day)], dtype=bool)
    ]
    if c.family == "F1":
        sp, pump = c.spec, c.spec["pump"]
        onset, failure = sp["onset"].floor("D"), sp["failure"]
        mine = inv[inv.pump_id == pump]
        caught = mine[(mine.day >= onset) & (mine.day + pd.Timedelta(days=1) <= failure)]
        watch = win[(win.pump_id == pump) & win.status.isin(["WATCH", "INVESTIGATE"]) & (win.day >= onset)]
        first = caught.day.min() if len(caught) else None
        wfirst = watch.day.min() if len(watch) else None
        lead = (
            (failure - (first + pd.Timedelta(days=1))).total_seconds() / 86400 if first is not None else 0.0
        )
        wlead = (
            (failure - (wfirst + pd.Timedelta(days=1))).total_seconds() / 86400 if wfirst is not None else 0.0
        )
        res.update(
            loss=sp["loss_24h"],
            ramp=sp["ramp_days"],
            caught=first is not None,
            lead_d=max(lead, 0.0),
            watch_lead_d=max(wlead, 0.0),
            false_escalation=bool(len(inv[inv.day < onset])),
            false_escalation_attributable=bool(len(attributable[attributable.day < onset])),
            headline=sp["loss_24h"] >= 0.20 and sp["ramp_days"] >= 7,
        )
    elif c.family in ("F2", "F3", "F4", "F7"):
        res.update(false_escalation=bool(len(inv)), false_escalation_attributable=bool(len(attributable)))
    elif c.family == "F5":
        out_days = inv[
            (inv.day >= c.spec["start"].floor("D"))
            & (inv.day <= c.spec["start"] + pd.Timedelta(hours=c.spec["hours"]))
        ]
        m = b.get("minutes_to_offline")
        out_attr = [
            d_ for p_, d_ in zip(out_days.pump_id, out_days.day) if (p_, d_) not in (background or set())
        ]
        res.update(
            minutes_to_offline=m,
            passed=m is not None and m <= 10 and not len(out_days),
            passed_attributable=m is not None and m <= 10 and not out_attr,
        )
    elif c.family == "F6":
        kind = c.spec["kind"]
        if kind in ("duplicate_rows", "repeated_starts"):
            clean = detect.run(b["clean_table"], P)
            same = clean[(clean.day >= c.start) & (clean.day < c.end)]["status"].to_numpy()
            passed = b["counts"].get(REQUIRED_F6[kind], 0) > 0 and (same == win["status"].to_numpy()).all()
        else:
            passed = REQUIRED_F6[kind] in b.get("realtime_flags", [])
        res.update(kind=kind, passed=bool(passed))
    return res


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def g6(P: params.Params, year: int) -> dict:
    out = {}
    for st in data.STATIONS:
        r = detect.run(real_table(st, f"{year + 1}-01-01"), P)
        y = r[r.day.dt.year == year]
        opens = y[y.status == "INVESTIGATE"].incident_id.nunique()
        out[st] = round(opens / len(station(st).pumps) / (365 / 180), 3)
    return out


def summarize(rows: list[dict], P: params.Params, year: int, runtime_s: float) -> dict:
    df = pd.DataFrame(rows)
    f1 = df[df.family == "F1"]
    head = f1[f1.headline]
    k, n = int(head.caught.sum()), len(head)
    lo, hi = wilson(k, n)
    fe = {
        f: f"{int(df[df.family == f].false_escalation.sum())}/{int((df.family == f).sum())}"
        for f in ("F2", "F3", "F4", "F7")
    }
    fe_attr = {
        f: f"{int(df[df.family == f].false_escalation_attributable.sum())}/{int((df.family == f).sum())}"
        for f in ("F2", "F3", "F4", "F7")
    }
    g6v = g6(P, year)
    f5, f6 = df[df.family == "F5"], df[df.family == "F6"]
    gates = {
        "G1": bool(f5.passed.all()),
        "G1_attributable": bool(f5.passed_attributable.all()),
        "G2": bool(f6.passed.all()),
        "G3": None,  # asserted by test_no_lookahead / test_determinism
        "G4": None,  # asserted by test_high_level_fires_and_has_no_inhibition_path
        "G5": all(v.startswith("0/") for v in fe.values()),
        "G5_attributable": all(v.startswith("0/") for v in fe_attr.values()),
        "G6": all(v <= 1.0 for v in g6v.values()),
        "G7": None,  # asserted by test_g7_no_warning_run_reproduces_record
    }
    return {
        "model_version": P.version,
        "params": {k2: getattr(P, k2) for k2 in ("k", "U", "h_w", "h_i", "W", "G", "min_effect")},
        "f1_recall": {
            "k": k,
            "n": n,
            "value": round(k / n, 4) if n else None,
            "wilson95": [round(lo, 4), round(hi, 4)],
            "scope": "loss >= 20% and ramp >= 7 d",
            "stations": 3,
            "years": 1,
        },
        "lead_days": {
            "median": round(float(f1.lead_d.median()), 2),
            "p10": round(float(f1.lead_d.quantile(0.1)), 2),
            "n": len(f1),
            "misses_as_zero": True,
        },
        "watch_lead_days": {"median": round(float(f1.watch_lead_d.median()), 2)},
        "f1_false_escalation_before_onset": int(f1.false_escalation.sum()),
        "false_escalations": fe,
        "false_escalations_attributable": fe_attr,  # excludes INVESTIGATE also present in the clean window
        "f1_false_escalation_before_onset_attributable": int(f1.false_escalation_attributable.sum()),
        "g6_investigate_opens_per_pump_per_180d": g6v,
        "f5_minutes_to_offline": {
            "median": float(f5.minutes_to_offline.median()) if len(f5) else None,
            "max": float(f5.minutes_to_offline.max()) if len(f5) else None,
        },
        "f6_pass": f"{int(f6.passed.sum())}/{len(f6)}",
        "gates": gates,
        "morningside_a_dev_lead_median_d": None,  # needs station_trip replays (replay_case); not built yet
        "runtime_s": round(runtime_s, 1),
    }


def _build_one(c: Case):
    return c, build(c)


def run(tier: str = "dev", P: params.Params | None = None, workers: int | None = None):
    if tier == "test" and os.environ.get("FREEZE") != "1":
        raise SystemExit("test tier is scored once per frozen version: set FREEZE=1 (§6.5)")
    P = P or params.load()
    t0 = time.time()
    cases = make_cases(tier)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        built = list(ex.map(_build_one, cases, chunksize=4))
    rows = [score(c, b, P) for c, b in built]
    summary = summarize(rows, P, TIERS[tier][0], time.time() - t0)
    out = ROOT / "reports" / tier
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
    pd.DataFrame(rows).to_csv(out / "cases.csv", index=False)
    return summary, rows, built


if __name__ == "__main__":
    s, _, _ = run(sys.argv[1] if len(sys.argv) > 1 else "dev")
    print(json.dumps(s, indent=2, default=str))
