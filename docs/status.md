# Build status map

Kept by Dhruv's agent. Updated at every merge or finding. Last update: frozen v2 (D6). Every claim here has a source: a merged PR, a test, or a measured run.

## Built and on main

| Piece | Evidence |
| --- | --- |
| Locked spec, `ARCHITECTURE.md` v2 | PRs #4, #8, #15 |
| Agent rules and code rules, `AGENTS.md` | PR #11 |
| Two locked scenarios (Morningside v1, Fishers v1) | PR #3, `test_scenarios` 3 passed |
| UI design tokens and test-id list | PR #9 |
| Vetted agent skills (fastapi, modern-python, tdd) | PR #14 |

## Built, in review (David's stack: #5 → #6 → #7 → #13)

| Piece | What it claims | Our own check |
| --- | --- | --- |
| Fixtures, QC, daily table (#6) | 9.5 MB, hashes match, rain invariance passes | Reviewer running |
| Detector (#7) | G6 passes on 2022 | Independent run reproduced his detector: 44371 P1 flagged 9 days before its 2022 outage; Morningside injection caught 10/10 |
| Outcome simulator, rain analog (#13) | G7: 14,532 vs 14,310 gal; 25,452 vs 25,000 gal | Reviewer running; analog SSE 13% measured independently |
| Scenario v2/v3 (#5) | Inflow raised to reach G7 | Allowed by §5.4 before 14:30 |

## Not built yet (due by the §15 schedule)

| Piece | Owner | Due |
| --- | --- | --- |
| `contracts.py`, `pyproject`, `Makefile`, `tools/verify`, CI, `fixtures/ui/` samples | Dhruv | 13:15 (**at risk: not started**) |
| `assess.py`, `explain.py`, REST API, MCP server, agent | Dhruv | 14:30 / 15:00 |
| `inject.py` (incl. `station_trip`), families, `evaluate.py` | David | 15:00 |
| Stations, drawer, Incidents, Lab screens | Praneetha | 15:45 (scaffold #10 held on 3 small items) |
| e2e + axe | Dhruv | 15:45 |
| Board watcher | Dhruv | demoted: interactive sessions cover it |

## Needs further validation

1. **G5 fails on the frozen v2 test run:** station shift 10/30 attributable false escalations (D6: no combination of the 648 passed on dev). G6 passes on test (0.00 / 0.16 / 0.74). **Disclosure:** the test tier was scored 1 time; no parameter may be changed because of it, and the headline claim must say so.
2. **The minimum effect size** was −8% in v1 (added after two 2023 cases reached INVESTIGATE on a −4.3% change) and is −12% in frozen v2, chosen on 2022 dev. It sits on the grid edge, so a wider grid is next.
3. **Morningside A measured lead depends on the 3,600 s run cap**, which the spec now defines. The ramp sweep is the honest answer, not the single number.
4. **The pump clock drifts up to ~2 days behind real time** in long injections. The storm-ahead story on screen must be checked in the actual replay.
5. **Fishers gallons saved** depend entirely on the assumed 180-minute discovery delay.
6. **Rain invariance** holds on 8 of 9 pumps measured; 45078 P3 (a lag pump) shows a 1.20 wet/dry ratio.

## Weak labels from the full dataset (all 24 stations, measured 13:00)

Labels = a busy pump with 0 runs for 2+ days while a sibling keeps running ("taken out of service", not "failed"). Script and outputs live in the session scratchpad; to be moved into `backend/scripts/` if we keep it.

- **117 episodes** across 18 of 24 stations. **44372 alone has 56** (median 2 days: likely duty rotation, not failure).
- **Only 16 of 117 (14%) were preceded by a capacity drop.** The other 101 show no warning sign in the data: sudden, planned, or rotation. No detector on this data could warn on those.
- **The detector warned on 7 of the 16 drop-type removals** (44%), and on 14 of 101 without a precursor.
- **Proxy precision is low:** 2023, 21 untouched stations: 2 of 41 INVESTIGATE incidents were followed by a removal within 30 days (5%). Many alerts may be real problems nobody pulled a pump for; we can't tell without maintenance logs.
- **Verdict:** too few clean labels to support "X of Y real failures caught" as a headline. Use it descriptively only.
- Both 2023 rows are test-tier numbers, seen once and disclosed; nothing may be tuned on them.

## Overreaching (what we must not say)

| Tempting claim | The truth | Say instead |
| --- | --- | --- |
| "Caught a real pump failure days early" | 44371 P1 went out of service for 4 days; cause unknown; may have been planned after operators saw the same thing | "A real pump's capacity fell 46% and stayed down; INVESTIGATE on day 2022-06-03 (raised 06-04 00:00Z), about 8 days before it was taken out of service on 06-11." |
| "Would have prevented the Morningside spill" | Mechanism unknown (clog vs sudden trip, tied at 40%); telemetry is a UK stand-in | "If it was a clog like the one reported upstream that week, a warning about 31 h ahead (first INVESTIGATE before the simulated trip) was possible in our rebuild." |
| "60% capacity loss detected" | On screen the measured change is about −31% (cap) | Show the measured number only |
| "Detects failures days ahead" | Only gradual mechanical loss; power, controller and vandalism failures are detected at onset at best | "Days ahead for gradual wear; minutes for silence; never for sudden faults." |
| "Rain-proof" | Rain-invariant on 8 of 9 pumps measured | "Barely moves with rain on the pumps we measured." |
| "Predicts pump failures" | 86% of real pump removals in the data had no visible precursor | "Catches gradual capacity loss, the kind that gives warning. Most removals in this data gave none." |
| "High precision on real data" | Proxy precision 5–19%; labels are removals, not failures | "Without maintenance logs, real-world precision is unmeasured; that's the pilot's first job." |
| Accuracy % without interval | n is small and windows overlap | Wilson interval and "n cases, 3 stations, 1 year" |

## Recalibration actions

1. Dhruv starts the integration skeleton now; it is the critical path for the UI.
2. David validates `min_effect` on 2022 only and logs the decision; no tuning on 2023.
3. Demo script uses the "Say instead" column verbatim.
4. Ignition stays P1 and is first to cut.
