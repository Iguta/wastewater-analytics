"""Write reports/data_quality.json: every §3.5 rule count and day-quality mix, per station.

Usage: python -m backend.scripts.data_quality_report
"""

import json
from pathlib import Path

from backend.app import data, features

END = "2024-01-01T00:00:00Z"
OUT = Path(__file__).resolve().parents[2] / "reports" / "data_quality.json"


def main() -> None:
    report = {"end_utc": END, "stations": {}}
    for st in data.STATIONS:
        s = data.load(st)
        counts = dict(s.quality_counts)
        t = features.daily_table(s.events, s.level, s.rain, END, st, counts)
        flags = t.explode("level_flags").dropna(subset=["level_flags"])
        report["stations"][st] = {
            "pumps": s.pumps,
            "events": len(s.events),
            "level_samples": len(s.level),
            "level_units": sorted(s.level["units"].astype(str).str.strip().unique()),
            "rule_counts": counts,
            "pump_day_quality": {p: g["quality"].value_counts().to_dict() for p, g in t.groupby("pump_id")},
            "level_flag_days": flags.drop_duplicates(["day", "level_flags"])["level_flags"]
            .value_counts()
            .to_dict(),
            "offline_hours_total": round(float(t.drop_duplicates("day")["offline_hours"].sum()), 2),
            "source_hash": s.source_hash,
        }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, default=int) + "\n")
    print(
        json.dumps(
            {
                k: v["level_flag_days"] | {"offline_h": v["offline_hours_total"]}
                for k, v in report["stations"].items()
            }
        )
    )


if __name__ == "__main__":
    main()
