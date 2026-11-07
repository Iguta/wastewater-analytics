"""Entry point for `make eval-smoke | eval-dev | eval-test` (ARCHITECTURE.md §6, §11.1).

smoke: 14 fixed dev cases (2 per family); asserts the harness runs and G1/G2 hold. G5 is printed, not
       asserted, until make tune freezes params (F7 is the known open flaw).
dev:   the full dev tier; writes reports/dev/summary.json, cases.csv and reports/evaluation.json.
test:  the 2023 test tier, once per frozen params version (FORCE=1 to repeat); aggregates only.
"""

import json
import sys

from backend.app import evaluate as E


def main(mode: str) -> int:
    if mode == "smoke":
        _, results, _ = E.run("dev", families={f: 2 for f in E.FAMILIES})
        s = results["C"][1]
        print(
            json.dumps(
                {k: s[k] for k in ("f1_recall_loss20_ramp7", "false_escalations", "gates")}, default=str
            )
        )
        return 0 if s["gates"]["G1"] and s["gates"]["G2"] else 1
    s, _, _ = E.run(mode)
    print(json.dumps(s, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "dev"))
