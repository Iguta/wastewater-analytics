# Model card: Dragonfly capacity-loss detector

Version `dragonfly-ci-v2-tuned` (`backend/app/params.toml`). Sources: `ARCHITECTURE.md` (A§), `docs/status.md`, `docs/evidence/`, `reports/`, and the measured runs named per line.

**Headline (A§6.7).** Test tier, scored 1 time: on 125 held-out synthetic capacity-loss injections into real 2023 Wessex telemetry (≥20% loss over ≥7 days), Dragonfly raised INVESTIGATE before the pump trip in 125/125 (Wilson 95% 97.0–100%; 125 cases from 3 stations, 1 year), a median 4.8 days ahead. The test tier was scored 1 time. Numbers marked *dev tier* are 2022, where tuning was allowed; v1 rows are labeled v1.

## 1. What it is

Dragonfly is a read-only early warning for lift-station pump capacity loss. From nothing but each pump's on/off timestamps it computes a capacity index (well-volumes per hour, in which inflow cancels by physics, A§4.1), tracks it against that pump's own trailing baseline with a CUSUM, and raises WATCH or INVESTIGATE when capacity falls and stays down (A§4.4-4.6). It is rules and statistics, not a trained model.

## 2. Intended use / not for

Use: tell an operator or planner which pump to inspect, how urgent, and why, days ahead for gradual wear (A§1, `docs/status.md`).

Not for:
- Failure probability or failure date. Forbidden claims are listed in A§6.7.
- Suppressing or replacing SCADA alarms. `HIGH_LEVEL` is never inhibited (A§4.8, gate G4).
- Any control write (A§1 "Not building").
- Stations other than fixed-speed, level-controlled ones. VFD stations are out of scope (A§4.1).

## 3. Training and data

No neural network, no gradient boosting, no pretrained weights, and no failure labels exist anywhere in the data (A§4.3, A§2).

Fitted from data:
- Per-pump trailing baseline: median and MAD of `log(ci)` over days `[d-G-W, d-G-1]`, from that pump's own past only (A§4.4).
- Per-station silence and high-level thresholds from the trailing 60 days (A§4.8).
- Six global hyperparameters (`k, U, h_w, h_i, W, G`) plus `min_effect`, about 7 tuned settings, grid-searched on 2022 dev only: 648 combinations (324 × `min_effect` {−8, −12}%) (A§4.14, `params.toml`, `reports/decisions.md` D6). `W`, `G` and `min_effect` sit on the grid edge; a wider grid is next.

Data roles (A§3.1):

| Source | Role | Effect on alert status |
| --- | --- | --- |
| Wessex run/stop events | Only input to the pump detector | Decides it |
| Wessex wet-well level | Safety pass-through, sensor checks, evidence | Safety or quality findings only |
| Wessex hourly rainfall | Evidence context; picks storm cases and Indiana analogs | None |
| Wessex signal key | Signal to station and pump map | None |
| Wessex flow and pressure | Not used (1,500-row samples only) | None |
| Bloomington SSO dataset | Builds Morningside; validates storm readiness | None |
| Open-Meteo archive and previous-runs forecast | Indiana rainfall; storm outlook | None; reorders queue only |
| News and IDEM records | Fishers scenario facts | None |

Tiers: dev = 2022 (tuning allowed), test = 2023 (score only) (A§3.3, A§6.1). Demo stations: 44371, 45385, 45078 (A§3.2).

Versions and hashes:
- Model version `dragonfly-ci-v2-tuned`; frozen parameters: `k=1.0, U=4, h_w=4, h_i=8, W=45, G=7, min_effect=-12` (`params.toml`). v1 was `k=0.5, h_w=3, h_i=6, W=60, G=14, min_effect=-8`.
- `source_hash` in every response is the sha256 of `fixtures/wessex/manifest.json` (A§3.4).
- Source file sha256 (A§3.4): `sps-run-stop-data.csv` `a630f8948e86acd9efacc378b260bd970de371fad40bc2ad871df38f40054f58`; `sps-wet-well-level-data.zip` `3f19794fb26909e95ac6c59f027b76279fd2eb69f8c56f011db6c23614a4c50e`; `sps-local-rainfall-data.csv` `775df41d5b2bee4468b2c3c2de2b72f31f6d22604dc1f97c31907c559a2c26b8`; `rising-main-diameter-and-key-to-telemetry-signals.csv` `9f87789c1c5544df539b3e322ab5825e6731332ddabbf40a180012cf41ecb935`.

## 4. The validation ladder

Each rung has a "does not prove" line. Read it.

**1. Physics check** (real data, 9 pumps at 4 stations, 2022 only for the ratios below; `docs/evidence/ci_rain_check.txt`)
- Result: capacity-index wet/dry ratio 0.96-1.03 on 8 of 9 pumps (45078 P3, a lag pump, is 1.20) vs 1.09-1.33 for raw run time. Day-to-day IQR/median 0.03-0.11 vs 0.14-0.33.
- Proves: the index barely moves with rain and is much less noisy than run time.
- Does not prove: that it detects anything. 45078 P3 (a lag pump) has a wet/dry ratio of 1.20 (`docs/status.md`).

**2. Planted faults** (synthetic injections into real streams; David's harness, 3 stations)
- **Test 2023, scored 1 time:** F1 capacity loss (loss ≥20%, ramp ≥7 days, per A§6.2): caught 125/125, Wilson 95% 97.0–100%; median lead 4.8 days. False escalations storm / duty swap / transient / station shift: 0 / 0 / 0 / 10 of 30. G1–G4, G6 and G7 pass; G5 fails (station shift 10/30) and is published as failing (D6).
- **Dev 2022, v1 → v2:** caught 112/114 → 112/114 (Wilson 95% 93.8–99.5% on v2); median lead 8.4 → 6.3 days; false escalations storm / duty / transient / station shift 0/10/3/19 → 0/1/0/3 of 30; G6 max 0.99 → 0.49. v2 cut false alarms at the cost of about a day of warning.
- F5 power cut (dev, v2): `SOURCE_OFFLINE` within 9 min at most.
- Proves: the detector finds the faults we know how to plant and mostly ignores rain.
- Does not prove: performance on real failures. We wrote the injector, so these are the faults we thought of. Station shift (F7) is the known open flaw (section 5).

**3. Real precursor** (one event; dev data, seen during design; `docs/evidence/ci_rain_check.txt`, `reports/decisions.md` D3)
- 44371 P1 capacity fell 46% and stayed down; on v2, INVESTIGATE opens on 2022-06-04, about a week before the pump was taken out of service on 06-11 (out of service 06-11 to 06-15, cause unknown). On v1 it was 06-02.
- Proves: a real, unplanted capacity drop is visible and flagged.
- Does not prove: a rate. n = 1, we saw it while designing, and the removal may have been planned after operators saw the same thing.

**4. Weak labels across the 24-station dataset** (2022-2023, so includes test-tier 2023 data seen once) ; measurement only, scratch run, not shown in the UI; A§6.8, `docs/status.md`
- 117 out-of-service episodes in the 24-station dataset (18 stations had at least one); 16 preceded by a capacity drop; the detector warned on 7 of those 16; 101 showed no sign.
- Proves: how much warning the data can contain at all (16 of 117).
- Does not prove: precision or "X of Y failures caught". Labels mean taken out of service, not failed; they mix planned work and rotation (44372 alone has 56). Descriptive only. The split of these counts into the 21 untouched stations vs the 3 demo stations is not reported in any file on main.

**5. Indiana what-ifs** (rebuilds on real Wessex telemetry; no Indiana telemetry exists; the Morningside runs use 2023 test-tier data, seen once and disclosed)
- Morningside A (v2 locked replay, 44371 stand-in): first INVESTIGATE raised 2024-04-10 00:00Z, about 31 h before the simulated trip at 04-11 07:00Z. Simulated overflow: no warning 14,532 gal (record 14,310); with a 24 h response 0; with 48 h or 96 h 14,532. Morningside B: no INVESTIGATE; `HIGH_LEVEL` 18 min after failure. The v1 ramp sweep (3/6/10/14 d) was not re-run on v2.
- Fishers silent-station (power failure, dead backup battery; A§2): A, `SOURCE_OFFLINE` at 9 min against a 5-minute target (reported, not gated). Simulated gallons at discovery 60/180/360 min: 22,912 / 17,049 / 8,068. B: `HIGH_LEVEL` at 34 min.
- Proves: the detector behaves sensibly on the shape of two documented Indiana events.
- Does not prove: that it would have caught them. Morningside's mechanism is unknown (clog vs sudden trip, tied at 40%), the lead assumes a gradual ramp, and telemetry is a UK stand-in (`docs/status.md`).

**6. Stress tests and gates** (A§6.3; test tier numbers as in rung 2)
- Gates G1-G7 must pass before a version freezes. G6 real INVESTIGATE opens per pump per 180 days, limit 1.0 (44371 / 45385 / 45078): test 0.00 / 0.16 / 0.74; dev max 0.49. G3 (`test_no_lookahead`, `test_determinism`) and G4 are tests.
- Learned baselines tested and not adopted: LightGBM with own lags 16/40 vs 23/40 for the rolling median (A§4.16); exogenous-only spread 0.67x, false opens 3 vs 1, and cycle-weighted z with no effect (board RESULT posts, 13:20, dev tier, scratch harness).
- Proves: storms (F2) and sensor faults (F6) are handled, and the simple baseline beat the learned ones. **Not met:** G5 requires 0 attributable false escalations; on test, station shift is 10/30. No combination of the 648 passed G5 on dev, so D6 froze the best and G5 is published as failing.
- Does not prove: real-world precision. The test tier was scored 1 time and nothing may be tuned on it. (v1 on the 2023 replay had 1.48 opens at 45385 against the limit of 1.0; v2 has 0.16.)

## 5. Known limitations

- **Station-shift leakage:** 10/30 false escalations on test (dev 3/30; v1 dev 19/30). G5 fails. Open.
- **Most removals give no warning:** 101 of 117 (86%) show no precursor (A§6.8, `docs/status.md`).
- **Check-valve failure is hidden:** it is not visible in on/off timing. This is a design limit; no file on main measures it.
- **Dual-pump wear looks station-wide:** both pumps wearing together look like a setpoint change, escalated on size alone at -30% for 3 days (A§4.7).
- **VFD stations are out of scope** (A§4.1).
- **UK telemetry stands in for Indiana** (A§2, `docs/status.md`).
- **Expected run time is not yet computed**: A§4.13 specifies it, and the explanation says "expected run time not yet computed" (`backend/app/explain.py`).
- **Test tier scored 1 time**; disclosed with every headline (`docs/status.md`).
- **A loss lasting longer than W+G = 74 days is absorbed into the baseline** and clears (A§4.4).
- **Real-world precision is unmeasured.** The 5-19% proxy figure uses removals, not failures (A§6.8, `docs/status.md`).

## 6. How it is kept honest

- Dev (2022) and test (2023) tiers; tuning on dev only (A§6.1).
- The test tier is scored once per frozen version; `make eval-test` refuses a second run and appends to `reports/test_runs.jsonl` (A§6.5).
- Gates, params and locked scenarios are CODEOWNERS-protected; an author cannot approve their own change (A§11.3, `.github/CODEOWNERS`).
- Per-PR benchmark against `main` on identical dev cases, with FAIL and REGRESSION flags (A§11.6).
- Agent grounding check: at least 19 of 20 fixed questions must pass (A§11.2, `make agent-eval`; local only today).
- Experiment log: every experiment is announced with its decision rule, and every result is logged in `reports/decisions.md`, including losses (`AGENTS.md`). Weak labels are never tuned on (A§6.8).

## 7. Path to production (roadmap, not done)

- Shadow-mode pilot at one utility alongside existing alarms.
- Operator "was this right?" feedback and maintenance records as real labels, fed into the benchmark (A§6.8, A§20).
- Champion/challenger: a new version must beat the current one on the same cases before it replaces it.
- Conformal false-alarm guarantee for the alert rate.
- Alarm budget per ISA-18.2.
- Read-only historian connectors.
- Drift monitors on the capacity index and baseline.
