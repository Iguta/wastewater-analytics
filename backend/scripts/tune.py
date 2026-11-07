"""make tune: grid search on the DEV tier only (ARCHITECTURE.md §4.14, §6.4). Writes reports/dev/grid.csv.

Objective: maximize F1 dev recall (loss >= 20%, ramp >= 7 d) subject to G1, G2, G5 and G6; tie-breaks: higher
median lead, then fewer real 2022 WATCH opens. G5/G1 use attributable escalations (absent from the clean
station replay) pending the gate-owner decision; raw counts are written alongside.
Daily tables are param-independent: built once, shared with workers by fork.
"""

import itertools
import multiprocessing as mp
import sys
import time
from pathlib import Path

import pandas as pd

from backend.app import data, detect, params
from backend.app import evaluate as E

GRID = {
    "k": [0.25, 0.5, 1.0],
    "U": [3, 4],
    "h_w": [2, 3, 4],
    "h_i": [5, 6, 8],
    "W": [45, 60, 90],
    "G": [7, 14],
    "min_effect": [-5.0, -8.0, -12.0],
}
OUT = Path(__file__).resolve().parents[2] / "reports" / "dev" / "grid.csv"
BUILT: list = []
REAL: dict = {}


def evaluate_combo(combo: dict) -> dict:
    P = params.load().with_(**combo)
    bg, g6, watch = {}, {}, 0
    for st, t in REAL.items():
        r = detect.run(t, P)
        bg[st] = set(zip(r[r.status == "INVESTIGATE"].pump_id, r[r.status == "INVESTIGATE"].day))
        y = r[r.day.dt.year == 2022]
        npump = len(E.station(st).pumps)
        g6[st] = y[y.status == "INVESTIGATE"].incident_id.nunique() / npump / (365 / 180)
        watch += y[y.status.isin(["WATCH", "INVESTIGATE"])].incident_id.nunique()
    rows = [E.score(c, b, P, background=bg[c.station]) for c, b in BUILT]
    df = pd.DataFrame(rows)
    f1 = df[df.family == "F1"]
    head = f1[f1.headline]
    out = dict(combo)
    out.update(
        recall=head.caught.mean(),
        recall_k=int(head.caught.sum()),
        recall_n=len(head),
        lead_median=f1.lead_d.median(),
        lead_p10=f1.lead_d.quantile(0.1),
        f1_pre_onset_attr=int(f1.false_escalation_attributable.sum()),
        g6_max=max(g6.values()),
        real_watch_opens=watch,
        G1=bool(df[df.family == "F5"].passed_attributable.all()),
        G2=bool(df[df.family == "F6"].passed.all()),
    )
    for f in ("F2", "F3", "F4", "F7"):
        out[f"fe_{f}"] = int(df[df.family == f].false_escalation_attributable.sum())
        out[f"fe_{f}_raw"] = int(df[df.family == f].false_escalation.sum())
    out["G5"] = all(out[f"fe_{f}"] == 0 for f in ("F2", "F3", "F4", "F7"))
    out["G6"] = out["g6_max"] <= 1.0
    out["feasible"] = out["G1"] and out["G2"] and out["G5"] and out["G6"]
    for st, v in g6.items():
        out[f"g6_{st}"] = round(v, 3)
    return out


def main(limit: int | None = None) -> None:
    t0 = time.time()
    cases = E.make_cases("dev")
    print(f"dropped {E.DROPPED.get('dev')}", flush=True)
    with mp.get_context("fork").Pool() as pool:
        BUILT.extend(pool.map(E._build_one, cases, chunksize=4))
    for st in data.STATIONS:
        REAL[st] = E.real_table(st, "2023-01-01")
    print(f"built {len(BUILT)} cases in {time.time() - t0:.0f} s", flush=True)
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())][:limit]
    with mp.get_context("fork").Pool() as pool:
        res = []
        for i, r in enumerate(pool.imap_unordered(evaluate_combo, combos, chunksize=2)):
            res.append(r)
            if i % 50 == 0:
                print(f"{i}/{len(combos)} combos, {time.time() - t0:.0f} s", flush=True)
    g = pd.DataFrame(res)
    g["fe_total"] = g[[f"fe_{f}" for f in ("F2", "F3", "F4", "F7")]].sum(axis=1)
    # §6.4: max recall subject to the gates; if nothing is feasible, fewest attributable false escalations first
    g = g.sort_values(
        ["feasible", "fe_total", "recall", "lead_median", "real_watch_opens"],
        ascending=[False, True, False, False, True],
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    g.to_csv(OUT, index=False)
    print(g.head(10).to_string(index=False))
    print(f"feasible {int(g.feasible.sum())}/{len(g)}; total {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
