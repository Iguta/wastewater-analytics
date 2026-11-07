"""Dev/test evaluation over the synthetic families F1-F7 and the real replay (ARCHITECTURE.md §5.6, §6).

`python -m backend.app.evaluate dev` writes reports/dev/summary.json (§11.6 keys) and reports/dev/cases.csv.
Daily feature tables are param-independent, so they are built once per case and cached in memory for tuning.
The test tier is scored only at freeze: `evaluate test` refuses to run without FREEZE=1.
"""

from __future__ import annotations

import json
import math
import os
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
DROPPED: dict = {}


@cache
def station(st: str) -> data.StationData:
    return data.load(st)


@cache
def real_table(st: str, end: str) -> pd.DataFrame:
    s = station(st)
    return features.daily_table(s.events, s.level, s.rain, end, st)


@cache
def proxy_windows(st: str, tier: str) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """§5.7 episodes (busy pump 0 runs >= 2 days while a sibling runs >= 10) at one station, for rejection.
    Reads only the tier's own year: the dev tier never touches 2023 data."""
    year = TIERS[tier][0]
    t = real_table(st, f"{year + 1}-01-01")
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


@cache
def eligible_pumps(st: str, start: pd.Timestamp, tier: str) -> list[str]:
    """§5.6: F1 injects only into pumps with >= 20 valid cycles on >= 30 of the 74 baseline days."""
    t = real_table(st, f"{TIERS[tier][0] + 1}-01-01")
    base = t[(t.day >= start - pd.Timedelta(days=74)) & (t.day < start)]
    ok = base[base.valid_cycles >= 20].groupby("pump_id").size()
    return sorted(ok[ok >= 30].index)


@dataclass
class Case:
    case_id: str
    family: str
    station: str
    start: pd.Timestamp  # first scored day
    end: pd.Timestamp  # exclusive
    spec: dict


def _window(rng, tier: str, st: str, center=None):
    """120-day scored window with W + G (74) days of real history before it, clear (+-14 d) of every proxy
    episode and the real 2023-08 outage. Returns None when no clean window is found in 200 draws."""
    year = TIERS[tier][0]
    lo = max(pd.Timestamp(f"{year}-01-01"), pd.Timestamp("2022-03-16"))
    hi = pd.Timestamp(f"{year + 1}-01-01") - pd.Timedelta(days=WINDOW_DAYS)
    bad = [*proxy_windows(st, tier), REAL_OUTAGE]
    for _ in range(200):
        if center is not None:
            s = min(max((center - pd.Timedelta(days=WINDOW_DAYS // 2)).floor("D"), lo), hi)
            center = None
        else:
            s = lo + pd.Timedelta(days=int(rng.integers(0, max(1, (hi - lo).days))))
        e = s + pd.Timedelta(days=WINDOW_DAYS)
        if all(e < a - pd.Timedelta(days=14) or s > b + pd.Timedelta(days=14) for a, b in bad):
            return s, e
    return None


def make_cases(tier: str, families=FAMILIES) -> list[Case]:
    """Deterministic §5.6 cases. A draw whose window would overlap a proxy episode or the outage, or (F1)
    whose station has no eligible pump, redraws the station; after 10 tries the case is dropped and counted
    in DROPPED[tier]."""
    year, base = TIERS[tier]
    cases = []
    DROPPED[tier] = {}
    for fam, n in families.items():
        for i in range(n):
            seed = base + i
            rng = np.random.default_rng([int(fam[1]), seed])  # family in the seed: see decisions.md D5
            for _try in range(10):
                st = str(rng.choice(data.STATIONS))
                center = None
                if fam == "F2":
                    rain = station(st).rain.set_index("ts_hour")["mm"].resample("D").sum(min_count=20)
                    wet = rain[rain.index.year == year].nlargest(30).index
                    center = wet[i % len(wet)]
                win = _window(rng, tier, st, center)
                if win is None:
                    continue
                s, e = win
                pumps = eligible_pumps(st, s, tier) if fam == "F1" else station(st).pumps
                if pumps:
                    break
            else:
                DROPPED[tier][fam] = DROPPED[tier].get(fam, 0) + 1
                continue
            spec: dict = {"wet_day": center} if fam == "F2" else {}

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


def build(c: Case, keep_stream: bool = False) -> dict:
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
    if keep_stream:  # replay_case needs the injected stream; the tuner must not carry it (memory)
        out["stream"] = sd
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


def score(c: Case, b: dict, P: params.Params, background: set | None = None, runner=None) -> dict:
    """Score one case. `background` = (pump, day) INVESTIGATE set of the un-injected data; when None it is
    computed from the case's own clean window (exact), the tuner passes a whole-station clean run (fast)."""
    runner = runner or detect.run
    r = runner(b["table"], P)
    win = r[(r.day >= c.start) & (r.day < c.end)]
    inv = win[win.status == "INVESTIGATE"]
    res = {"case_id": c.case_id, "family": c.family, "station": c.station}
    if background is None and "clean_table" in b:
        rc = runner(b["clean_table"], P)
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
            clean = runner(b["clean_table"], P)
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


def _trailing(g: pd.DataFrame, col: str, P: params.Params, fn) -> np.ndarray:
    v, d = g[col].to_numpy(dtype=float), (g.day - g.day.min()).dt.days.to_numpy()
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        w = v[(d >= d[i] - P.G - P.W) & (d <= d[i] - P.G - 1)]
        w = w[~np.isnan(w)]
        if len(w) >= P.min_baseline_days:
            out[i] = fn(w)
    return out


def bench_a(t: pd.DataFrame, P: params.Params, r_i: float = 1.5) -> pd.DataFrame:
    """§4.15 A, simple rule: daily median run time vs its trailing median. No QC, persistence or siblings."""
    parts = []
    for _p, g in t.sort_values("day").groupby("pump_id"):
        g = g.copy()
        ratio = g.run_median_s.to_numpy(dtype=float) / _trailing(g, "run_median_s", P, np.median)
        g["status"] = np.where(
            ratio > r_i, "INVESTIGATE", np.where(ratio > 1 + (r_i - 1) / 2, "WATCH", "NORMAL")
        )
        parts.append(g)
    return _opens(pd.concat(parts, ignore_index=True))


def bench_b(t: pd.DataFrame, P: params.Params, z_i: float = 5.0) -> pd.DataFrame:
    """§4.15 B, physics only: single-day z of log CI vs trailing median/MAD. All days, no siblings."""
    parts = []
    for _p, g in t.sort_values("day").groupby("pump_id"):
        g = g.copy()
        g["logci"] = np.log(g.ci)
        med = _trailing(g, "logci", P, np.median)
        mad = _trailing(g, "logci", P, lambda w: np.median(np.abs(w - np.median(w))))
        z = (g.logci.to_numpy() - med) / np.maximum(1.4826 * mad, 0.01)
        g["status"] = np.where(z < -z_i, "INVESTIGATE", np.where(z < -(z_i - 2), "WATCH", "NORMAL"))
        parts.append(g)
    return _opens(pd.concat(parts, ignore_index=True))


def _opens(r: pd.DataFrame) -> pd.DataFrame:
    """incident_id for the simple benchmarks: one per run of consecutive INVESTIGATE days."""
    r = r.sort_values(["pump_id", "day"]).reset_index(drop=True)
    inv = r.status == "INVESTIGATE"
    new = inv & ~(inv.groupby(r.pump_id).shift(fill_value=False))
    r["incident_id"] = (r.pump_id + ":" + new.groupby(r.pump_id).cumsum().astype(str)).where(inv)
    return r


BENCHMARKS = {
    "A": (bench_a, {}),
    "B": (bench_b, {}),
    "C": (None, {}),
    "C-persistence": (None, {"persistence": False}),
    "C-inhibition": (None, {"inhibition": False}),
    "C-quality": (None, {"quality_gate": False}),
}


def g6(P: params.Params, year: int, runner=None) -> dict:
    runner = runner or detect.run
    out = {}
    for st in data.STATIONS:
        r = runner(real_table(st, f"{year + 1}-01-01"), P)
        y = r[r.day.dt.year == year]
        opens = y[y.status == "INVESTIGATE"].incident_id.nunique()
        out[st] = round(opens / len(station(st).pumps) / (365 / 180), 6)
    return out


LOSS_BINS = [0.10, 0.20, 0.30, 0.40, 0.50]
RAMP_BINS = [3, 7, 14, 21, 30]


def summarize(rows: list[dict], P: params.Params, tier: str, runner=None) -> dict:
    """reports/<tier>/summary.json, keyed by the §11.6 table rows. Floats rounded to 6 dp (G3)."""
    df = pd.DataFrame(rows)
    f1 = df[df.family == "F1"]
    head = f1[f1.headline]
    k, n = int(head.caught.sum()), len(head)
    lo, hi = wilson(k, n)
    fam = {"F2": "storm", "F3": "duty_swap", "F4": "transient", "F7": "station_shift"}

    def kn(col, f):
        d = df[df.family == f]
        return {"k": int(d[col].sum()), "n": len(d)}

    g6v = g6(P, TIERS[tier][0], runner)
    f5, f6 = df[df.family == "F5"], df[df.family == "F6"]
    fe_attr = {f: kn("false_escalation_attributable", f) for f in fam}
    bins = []
    f1 = f1.assign(lb=pd.cut(f1.loss, LOSS_BINS, right=False), rb=pd.cut(f1.ramp, RAMP_BINS, right=False))
    for (lb, rb), g in f1.groupby(["lb", "rb"], observed=True):
        bk, bn = int(g.caught.sum()), len(g)
        blo, bhi = wilson(bk, bn)
        bins.append(
            {
                "loss": [lb.left, lb.right],
                "ramp_days": [rb.left, rb.right],
                "k": bk,
                "n": bn,
                "wilson95": [round(blo, 6), round(bhi, 6)],
                "shown": bn >= 20,
            }
        )
    summary = {
        "model_version": P.version,
        "params": {k2: getattr(P, k2) for k2 in ("k", "U", "h_w", "h_i", "W", "G", "min_effect")},
        "f1_recall_loss20_ramp7": {"k": k, "n": n, "wilson95": [round(lo, 6), round(hi, 6)]},
        "f1_recall_bins": bins,
        "lead_days": {
            "median": round(float(f1.lead_d.median()), 6),
            "p10": round(float(f1.lead_d.quantile(0.1)), 6),
            "n": len(f1),
            "misses_as_zero": True,
        },
        "false_escalations": {fam[f]: v for f, v in fe_attr.items()},
        "false_escalations_raw": {fam[f]: kn("false_escalation", f) for f in fam},
        "f1_investigate_before_onset": {
            "attributable": int(f1.false_escalation_attributable.sum()),
            "raw": int(f1.false_escalation.sum()),
        },
        "real_2022_investigate_opens_per_pump_180d": g6v,
        "gates": {
            "G1": bool(f5.passed_attributable.all()),
            "G2": bool(f6.passed.all()),
            "G5": all(v["k"] == 0 for v in fe_attr.values()),
            "G6": all(v <= 1.0 for v in g6v.values()),
            # G3, G4, G7 are asserted by tests (no-lookahead/determinism, HIGH_LEVEL inhibition, G7 sim)
        },
        "gates_raw": {
            "G1": bool(f5.passed.all()),
            "G5": all(df[df.family == f].false_escalation.sum() == 0 for f in fam),
        },
        "f5_minutes_to_offline_max": float(f5.minutes_to_offline.max()) if len(f5) else None,
        "morningside_a_dev_lead_median_d": None,  # needs station_trip replays; next PR
        "cases_dropped": DROPPED.get(tier, {}),
    }
    return summary


def evaluation_report(results: dict, P: params.Params) -> dict:
    """reports/evaluation.json in the §7 EvaluationReport shape (#33)."""
    bench = {}
    for name, (rows, s) in results.items():
        df = pd.DataFrame(rows)
        f1 = df[df.family == "F1"]
        head = f1[f1.headline]

        def kn(f, df=df):
            d = df[df.family == f]
            return {"k": int(d.false_escalation_attributable.sum()), "n": len(d)}

        bench[name] = {
            "caught": {"k": int(head.caught.sum()), "n": len(head)},
            "median_lead_days": round(float(f1.lead_d.median()), 6),
            "false_storm": kn("F2"),
            "false_duty": kn("F3"),
            "false_transient": kn("F4"),
            "real_alerts_per_pump_6mo": round(
                float(np.mean(list(s["real_2022_investigate_opens_per_pump_180d"].values()))), 6
            ),
        }
    c = results["C"][1]
    proxy = json.loads((ROOT / "reports" / "proxy_events.json").read_text())
    allst = json.loads((ROOT / "reports" / "proxy_events_all_stations.json").read_text())
    rows = [{"tier": "dev", "group": "demo_3", **proxy["demo_stations"]["counts"]["dev"]}]
    untouched = allst.get("untouched_stations", {}).get("counts", {}).get("dev")
    if untouched:
        rows.append({"tier": "dev", "group": "untouched_21", **untouched})
    return {
        "model_version": f"{P.version} (dev, untuned)" if not P.version.endswith("tuned") else P.version,
        "code_version": _code_version(),
        "benchmarks": bench,
        "heatmap": [
            {"loss": b["loss"][0], "ramp": b["ramp_days"][0], "k": b["k"], "n": b["n"]}
            for b in c["f1_recall_bins"]
        ],
        "proxy": rows,
        "test_scored": len(json.loads(TEST_LOCK.read_text())) if TEST_LOCK.exists() else 0,
        "gates": c["gates"],
    }


def _code_version() -> str:
    import subprocess

    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "backend"], capture_output=True, text=True, cwd=ROOT
        ).stdout.strip()
        return (sha + ("-dirty" if dirty else "")) or "unknown"
    except OSError:
        return "unknown"


def _jsonable(o):
    return o.item() if hasattr(o, "item") else str(o)


def _build_one(c: Case):
    return c, build(c)


TEST_LOCK = ROOT / "reports" / "test" / "scored.json"


def run(tier: str = "dev", P: params.Params | None = None, workers: int | None = None, families=FAMILIES):
    P = P or params.load()
    if tier == "test":  # §6.5: once per frozen params version, aggregates only
        scored = json.loads(TEST_LOCK.read_text()) if TEST_LOCK.exists() else {}
        if P.version in scored and os.environ.get("FORCE") != "1":
            raise SystemExit(f"test tier already scored for {P.version}; FORCE=1 overrides (§6.5)")
    cases = make_cases(tier, families)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        built = list(ex.map(_build_one, cases, chunksize=4))
    results = {}
    for name, (fn, switches) in BENCHMARKS.items():
        Pb = P.with_(**switches)
        runner = (lambda t, p, fn=fn: fn(t, p)) if fn else None
        rows = [score(c, b, Pb, runner=runner) for c, b in built]
        results[name] = (rows, summarize(rows, Pb, tier, runner))
    summary = results["C"][1]
    out = ROOT / "reports" / tier
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=_jsonable) + "\n")
    if tier == "dev":
        pd.DataFrame(results["C"][0]).round(6).to_csv(out / "cases.csv", index=False)
        report = evaluation_report(results, P)
        (ROOT / "reports" / "evaluation.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, default=_jsonable) + "\n"
        )
    else:
        scored = json.loads(TEST_LOCK.read_text()) if TEST_LOCK.exists() else {}
        scored[P.version] = pd.Timestamp.now(tz="UTC").isoformat()
        TEST_LOCK.write_text(json.dumps(scored, indent=2, sort_keys=True) + "\n")
    return summary, results, built
