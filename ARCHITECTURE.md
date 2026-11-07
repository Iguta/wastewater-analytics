# Dragonfly AI: Architecture and Locked Decisions

**Version 2, locked 2026-11-07 12:30 ET.** This replaces v1 (the build handoff, commit `a40d1e9`). Where it conflicts with PLAN.md, this file wins. Every line below is a decision, not an option.

**Rules for every human and agent**

1. Build exactly what is written here. If you need a decision that is not here, do not improvise. Post on the board (`tools/board post`), tag the owner of that decision (§17), and work on something else until it is answered.
2. A locked decision changes only through a PR labeled `decision-change` that edits this file. Announce it on the board; the decision's owner must approve it.
3. The numbers in this file were measured on the real data (§2). Quote no number that is not in this file or in a generated report.

## 1. What we are building

Dragonfly reads lift-station telemetry **read-only**. It measures each pump's pumping capacity from nothing but its on/off timestamps, and it raises an evidence-backed warning when one pump's capacity falls and stays down, before the pump fails. It never writes to a control system, never hides a safety alarm, and says plainly when it does not know.

```text
fixtures/ (real Wessex telemetry, scenario transforms)
   -> backend/app: QC -> daily capacity features -> detector -> assess (one implementation)
        -> contracts.py (Pydantic, validated)
             -> api.py (REST)       -> frontend/ (operator UI)
             -> mcp_server.py (MCP) -> any agent harness, plus agent.py (Claude Sonnet 5.5)
```

The detector and the alert rules decide everything. The MCP server only exposes their results. The agent only explains them. No model is trained or retrained while a request is being served.

**Not building:** a PLC or SCADA write path, a SCADA replacement, a CMMS, failure-probability or failure-date prediction, live utility connectors, notifications or paging, acknowledge/resolve workflow, user accounts, Ignition, a promo video, a cloud deployment.

## 2. The evidence behind these decisions

The analysis scripts and their raw outputs are in `docs/evidence/`.

| Fact | Measured value | Source |
| --- | --- | --- |
| Data available | Run/stop events per pump, wet-well level and hourly site rainfall for 24 stations, 2022–2023. Timestamps carry no timezone. No failure, burst or maintenance labels anywhere. Flow and pressure exist only as 1,500-row sample files. | Wessex data audit |
| Real outage in the data | Every station is silent from 2023-08-17 10:20 to 2023-08-20 12:21 | Audit `stn_gaps.csv` |
| The capacity index barely moves with rain | Wet days (≥10 mm) vs dry days: capacity index ratio 0.96–1.03 on 9 of 11 pumps. Raw median run time ratio is 1.14–1.33. | `docs/evidence/ci_rain_check.txt` |
| The capacity index is much less noisy | Day-to-day IQR/median: capacity index 0.03–0.11, raw run time 0.14–0.33 | same |
| It catches a real precursor | 44371 pump 1: index steady at about 30.0/h for three weeks, then 28.2 on 2022-05-31, 16.3 on 06-01 (−46%), 11.8 by 06-10. The pump then sat out of service from 06-11 to 06-15. | same |
| Whole-station shifts exist | At 45385, both pumps' index fell to 0.66× of 2022 in 2023, together. That is a station-level change (setpoints or force main), not pump wear. | same |
| Equipment failures cluster on wet days | Bloomington, 2005–2026, equipment-failure overflow days: 39% had ≥0.5 in rain, vs 8.2% of all days (4.7×) | `docs/evidence/public_signals.txt` |
| Power-loss overflows follow storms | ≥1 in rain on 31% of power-loss overflow days, vs 2.4% of all days (12.8×). Gusts ≥45 mph: 3.8×. | same |
| Blockages track the holiday grease season, weakly | 20% of blockage days fall Nov 20–Jan 5, vs 12.5% of all days (1.6×) | same |
| Forecasts as issued at the time are recoverable | For Morningside on 2024-04-11, the forecast made 2 days ahead said 0.98 in; 1.28 in fell | Open-Meteo previous-runs API |
| Morningside 2024-04-11 | "Equipment failure", 14,310 gal, same day, rain field 1.18 in, 2.5–2.7 in over Apr 8–11 (the total depends on grid point and window). Subtype, duration and response are unknown. Four days earlier there was an upstream blockage; starter contacts were replaced in 2023; the station was rebuilt in 2024. | Bloomington SSO dataset `kfaf-msfz`; CBU board documents (see the scenario file) |
| Fishers (HSE Utilities, Intracoastal at Geist) | 2009-01-20, about 06:00 EST: a power failure took down the station controller, whose backup battery was dead; 25,000 gal; dry weather. 2012-12-22: another overflow at the same manhole, followed by a $5,250 fine (case 2013-21374-W). | IBJ 2013-08-09; IDEM Agreed Order (seen only through search summaries); see the scenario file |

## 3. Data

### 3.1 Sources, their roles and their weight in the model

There are no learned weights across data sources. Each source has one fixed role.

| Source | Role | Effect on alert status |
| --- | --- | --- |
| Wessex run/stop events | The only input to the pump detector (capacity index, §4.1) | Decides it |
| Wessex wet-well level | Safety pass-through (`HIGH_LEVEL`), sensor checks, evidence chart | Can only add safety or quality findings |
| Wessex hourly rainfall | Context in the evidence. Selects storm-control cases and Indiana rain analogs. | None |
| Wessex signal key | Maps signal IDs to station and pump | None |
| Wessex flow and pressure | Not used: only 1,500-row samples exist | None |
| Bloomington SSO dataset (live Socrata API, 1,101 rows, 1996-01-17 to 2026-08-27) | Builds the Morningside scenario. Validates storm readiness. The Drive copy is not used. | None |
| Open-Meteo archive and previous-runs forecast | Indiana scenario rainfall. Storm-readiness outlook. | None; reorders the queue only (§4.12) |
| News and IDEM records | Fishers scenario facts | None |

Within the detector, every valid cycle counts once in its pump-day median, and every `SUFFICIENT` day counts once in the baseline median and MAD. Pumps are never pooled; stations are never pooled. Six global hyperparameters (§4.14) are the only quantities tuned across data.

### 3.2 Stations

| Station | Pumps | Why |
| --- | --- | --- |
| 44371 | 2 | Clean: 1-minute level, 5 h of level gaps in two years. Has the real 2022 precursor event. |
| 45385 | 2 | Clean, 1-minute level. Normal unequal duty split (about 1:2), which serves as the duty/standby control. Has the 2023 station-wide shift. |
| 45078 | 3 | Three-pump station, 1-minute level in mm. One 168 h level gap. |

**Not used:** 45497 (its 2023 run-time P90 jumps to 3,517 s, which suggests a control change) and 43014 (pump 1 out of service most of 2022, 5-minute level, 896 h of level gaps).

Display names are `Wessex 44371`, `Wessex 45385` and `Wessex 45078`. No fictional names are used.

### 3.3 Time and splits

- **Timezone:** naive timestamps are read as UTC, as recorded. Days are UTC dates. The API takes and returns `as_of_utc` in ISO 8601 with `Z`.
- **Warm-up:** the baseline needs 74 days of history. Real replay `as_of_utc` is therefore valid from `2022-03-16T00:00:00Z` to `2024-01-01T00:00:00Z`.
- **Dev tier** (tuning allowed): 2022. **Test tier** (score only): 2023. Per-pump baselines are trailing (§4.4), so the split controls only hyperparameter tuning and case generation.

### 3.4 Fixtures

- `backend/scripts/export_fixtures.py` reads the raw Wessex files from `$WESSEX_DIR`. They are never committed.
- It writes `fixtures/wessex/<station>/runstop.parquet` (`signal_id, ts, value`), `level.parquet` (`signal_id, ts, value, units`) and `rain.parquet` (`ts_hour, mm`), all zstd-compressed, raw rows unmodified. It also writes `fixtures/wessex/manifest.json` with source file names, sha256, rows exported and the filter used. Budget: 40 MB total.
- Source hashes as audited:

| File | sha256 |
| --- | --- |
| `sps-run-stop-data.csv` | `a630f8948e86acd9efacc378b260bd970de371fad40bc2ad871df38f40054f58` |
| `sps-wet-well-level-data.zip` | `3f19794fb26909e95ac6c59f027b76279fd2eb69f8c56f011db6c23614a4c50e` |
| `sps-local-rainfall-data.csv` | `775df41d5b2bee4468b2c3c2de2b72f31f6d22604dc1f97c31907c559a2c26b8` |
| `rising-main-diameter-and-key-to-telemetry-signals.csv` | `9f87789c1c5544df539b3e322ab5825e6731332ddabbf40a180012cf41ecb935` |

- `source_hash` in every response is the sha256 of `manifest.json`.

### 3.5 Quality rules

Every rule counts what it touches, and the counts go to `reports/data_quality.json`. Nothing is dropped silently.

| Rule | Flag | Action |
| --- | --- | --- |
| Unparseable timestamp | `BAD_TIMESTAMP` | Drop the row, count it |
| Exact duplicate row | `DUPLICATE_ROW` | Drop, count |
| Two starts in a row for the same pump | `REPEATED_START` | Keep the first start |
| Two stops in a row for the same pump | `REPEATED_STOP` | Keep the first stop |
| Start with no stop by end of data | `OPEN_RUN` | Exclude the run |
| Pairing | none | Pairs are formed within a pump only, never across pumps |
| Run under 5 s or over 3,600 s | `RUN_OUT_OF_RANGE` | Exclude from the capacity index; keep in the run count |
| Fill under 10 s or over 6 h | `FILL_OUT_OF_RANGE` | Exclude from the capacity index |
| Run starts before the previous run at the station ends | `OVERLAP` | Exclude from the capacity index; counts toward `overlap_share` |
| Level below 0, or above 105% for % units | `LEVEL_OUT_OF_RANGE` | Exclude the sample; `SENSOR_FAULT` if more than 1% of the day |
| Level unchanged for 6 h or more while pumps cycle | `LEVEL_FLATLINE` | `SENSOR_FAULT`; the high-level check becomes `UNKNOWN` |
| No level sample for 15 min or more | `LEVEL_GAP` | Missing, never filled in |
| Missing rain hour | `RAIN_GAP` | Stored as NaN, never 0. Daily rain needs 20 of 24 hours, otherwise rain context is `PARTIAL`. |
| Binary pump state | none | Never forward-filled across gaps |

### 3.6 Public signals considered

| Signal | Decision | Why |
| --- | --- | --- |
| Pump on/off timing as a hidden flow meter (capacity index) | **IN (core)** | Rain-invariant and 3–7× less noisy than run time (§2). This is our unorthodox signal: a pump-rate measurement from data every utility already logs and ignores. |
| Sibling pumps as a built-in control group | **IN (core)** | Subtracting the station's common shift separates pump wear from setpoint, force-main or inflow changes (45385, §2) |
| Archived 1–2 day-ahead weather forecasts (Open-Meteo previous-runs API) | **IN (queue ranking only, Indiana scenarios)** | Equipment failures are 4.7× and power losses 12.8× likelier on heavy-rain days. The forecast as issued then is recoverable, so the replay stays honest. |
| Observed rainfall | **IN (context only)** | Explains inflow in the evidence. The index does not need it. |
| Satellite imagery | OUT | The assets are underground; nothing visible changes before a pump fails |
| Power-grid outage feeds | OUT | No free historical API for Indiana. Forecast gusts and rain are the proxy (3.8× and 12.8×). |
| USGS stream gauges, groundwater, soil moisture | OUT | They describe infiltration and inflow, and the capacity index already cancels inflow |
| Holiday grease calendar | OUT | Only a 1.6× lift, and blockages are not what our detector targets |
| 311 complaints, social media | OUT | They come after the overflow, not before |
| IU football and academic calendar | OUT | They change inflow, which the index cancels |

## 4. Model

### 4.1 The capacity index

For each pump run *i*, `run_i` is the run length in seconds. `fill_i` is the gap between the end of the previous run of **any** pump at the station and the start of run *i*.

`CI_i = 3600/run_i + 3600/fill_i`, in well-volumes per hour.

Physics: during the fill the well rises one cycle volume `V` at inflow `Q_in`, so `fill = V/Q_in`. During the run it falls `V` at `Q_pump − Q_in`, so `run = V/(Q_pump − Q_in)`. Adding the reciprocals gives `Q_pump/V`, so inflow (rain) cancels. A worn or ragged pump pumps less, so its CI falls.

- **Valid cycle:** passes every rule in §3.5 (run 5–3,600 s, fill 10 s–6 h, no overlap).
- **Assumed:** fixed-speed pumps with fixed level setpoints. VFD-controlled stations are out of scope.

### 4.2 Daily features

There is one row per pump per UTC day. Days are complete only when strictly before the `as_of` date.

Columns: `station_id, pump_id, day, runs, valid_cycles, overlap_share, invalid_share, offline_hours, ci` (median CI of valid cycles), `run_median_s, fill_median_s, rain_mm, level_flags, quality`.

### 4.3 What is "trained"

There is no neural network, no gradient boosting and no pretrained weights. We have no failure labels to fit or check them against. The physics index already removes rain, and every number must be explainable to an operator. This reverses the 10:05 PLAN.md decision; see the decisions log there.

What is computed from data:

1. **Per-pump trailing baseline.** Median and MAD of `log(ci)`, recomputed for each day from that pump's own past days only (§4.4).
2. **Per-station thresholds.** The silence threshold and high-level threshold come from the trailing 60 days (§4.8).
3. **Six global hyperparameters**, picked by grid search on the dev tier (§4.14, §6.4) and frozen in `backend/app/params.toml` with a version string.

### 4.4 Baseline

For decision day `d`, the baseline window is days `[d−G−W, d−G−1]`, using only `SUFFICIENT` days. The defaults are `W = 60` and `G = 14`. The 14-day guard keeps a developing fault out of its own baseline.

- If fewer than 30 baseline days are available, the pump status is `INSUFFICIENT_EVIDENCE` with the reason "warming up".
- `z_d = (log ci_d − median) / max(1.4826·MAD, 0.01)`, clipped to [−10, 10].

### 4.5 Sibling inhibition

- Each day, `c_d` = median of `z` over the station's pumps with `SUFFICIENT` evidence that day. This applies only when there are at least 2 such pumps; otherwise `c_d = 0`, and the evidence notes that sibling comparison was unavailable.
- The pump-specific deviation is `u_d = z_d − c_d`.
- `c_d` is the station-wide signal (§4.7).

### 4.6 CUSUM and pump status

- **Update rule:** `S_d = max(0, S_{d−1} + clip(−u_d, −U, U) − k)`.
- **When it updates:** only on `SUFFICIENT` days. `PARTIAL`, `INSUFFICIENT` and `SOURCE_OFFLINE` days hold `S` unchanged.
- **Defaults:** `k = 0.5`, `U = 4`, `h_w = 3`, `h_i = 6`.

| Condition | Pump status |
| --- | --- |
| Fewer than 30 baseline days | `INSUFFICIENT_EVIDENCE` |
| `S ≥ h_i`, and at least 2 of the last 3 `SUFFICIENT` days have `u < −k` (persistence) | `INVESTIGATE` |
| `S ≥ h_w` | `WATCH` |
| Was `INVESTIGATE` | Stays until `S < h_w`, then becomes `WATCH` |
| Was `WATCH` | Stays until `S < 1.0`, then becomes `NORMAL` |
| Otherwise | `NORMAL` |

`capacity_change_pct = 100·(exp(log ci_d − median) − 1)`.

### 4.7 Station-wide change

- The same CUSUM runs on `−c_d`.
- At `S_station ≥ h_w`, it raises a `STATION_WIDE_CHANGE` finding at `WATCH`, never higher.
- Possible causes listed: level setpoint change, force-main restriction, control change, common supply issue.

### 4.8 Other findings

| Finding | Rule | Status | Where shown |
| --- | --- | --- | --- |
| `PUMP_NOT_RUNNING` | Baseline runs/day median ≥10, today 0 runs, and a sibling has ≥10 runs today | `WATCH` | Queue |
| `SOURCE_SILENT` | Either of two heartbeats has stopped before `as_of`: the level stream has missed 5 consecutive expected samples (5 min at 1-minute cadence), or no pump event has arrived for `T = max(20 min, 3 × P99 of fill times over the trailing 60 days)`. The level heartbeat makes 5-minute detection possible. | Station `SOURCE_OFFLINE` | Safety strip |
| `HIGH_LEVEL` | Level at or above the station's trailing 60-day P99.9 for 5 consecutive minutes within the 24 h before `as_of` | `INVESTIGATE` | Safety strip. Never suppressed or inhibited. Labeled "SCADA-equivalent; real setpoints unknown." |
| `SENSOR_FAULT` | A level flag from §3.5 | `WATCH` | Queue. `HIGH_LEVEL` becomes `UNKNOWN` and is listed in missing evidence. |

`SOURCE_SILENT` and `HIGH_LEVEL` use data up to `as_of`, at minute resolution. Every other finding uses complete days only.

### 4.9 Evidence quality per pump-day

| Quality | Rule |
| --- | --- |
| `SOURCE_OFFLINE` | More than 6 h of station silence that day |
| `SUFFICIENT` | `valid_cycles ≥ 20`, `overlap_share ≤ 0.2`, offline ≤ 1 h and `invalid_share ≤ 0.2` |
| `PARTIAL` | `valid_cycles` 5–19, overlap > 0.2, offline 1–6 h, or invalid > 0.2 |
| `INSUFFICIENT` | `valid_cycles < 5` |

- **Station quality:** the worst over its non-standby pumps. A standby pump is one whose baseline median is under 5 runs/day.
- **Sensor effect:** any `SENSOR_FAULT` caps station quality at `PARTIAL`.

### 4.10 Station status

Station status is the highest of the following, in this order: `SOURCE_OFFLINE`, `INVESTIGATE`, `WATCH`, `INSUFFICIENT_EVIDENCE`, `NORMAL`.

`INSUFFICIENT_EVIDENCE` applies only when no pump has `SUFFICIENT` or `PARTIAL` evidence.

### 4.11 Incidents and the attention queue (the "Dragonfly" layer)

The insect-vision analogy is a design analogy only. Each stage below is plain code.

| Dragonfly stage | Our code |
| --- | --- |
| Local detectors | Per-pump CI CUSUM, station CUSUM, `PUMP_NOT_RUNNING`, `SOURCE_SILENT`, `HIGH_LEVEL`, `SENSOR_FAULT` |
| Lateral (contextual) inhibition | Subtract the station's common shift (§4.5). Hold evidence on poor-quality days. Rain is **not** used to suppress anything. |
| Trajectory facilitation | CUSUM accumulation plus the 2-of-3-day persistence rule |
| Target tracking | One incident per `(scope, station, pump, finding type)`. `alert_id = {scope}:{station}:{pump or STATION}:{type}:{opened_on}`, where `scope` is `REAL` or the `scenario_id`. A recurrence within 7 days of closing reopens the same id. |
| Competitive attention | Safety strip first (`SOURCE_SILENT`, `HIGH_LEVEL`). Then the queue: `INVESTIGATE` by capacity loss % (largest first), then `WATCH` by days open. The top 5 are shown; the rest go under "Low priority (n)". Nothing is hidden. |

### 4.12 Storm readiness

- **Where:** only for `SIMULATED_INCIDENT` scenarios, which have real coordinates. Wessex stations have no public coordinates, so their outlook is `null` with that reason.
- **Data:** the forecast issued the day before `as_of`, from the Open-Meteo previous-runs API (`precipitation_previous_day1`, `wind_gusts_10m_previous_day2`, next 48 h). It is cached at scenario lock in `fixtures/scenarios/<id>.forecast.json`, so the demo makes no network calls.
- **`storm_ahead`:** forecast rain ≥0.5 in or a gust ≥45 mph.
- **Effect:** if `storm_ahead` and the station has a `WATCH` or `INVESTIGATE` pump finding, that finding moves up one priority level and the action reads "inspect before {storm date}". It never changes a status.

### 4.13 Numbers operators read

- **Expected run time today** = median over today's valid cycles of `3600 / (CI_baseline − 3600/fill_i)`. If the denominator is ≤0, show "pump would not keep up at today's inflow".
- **Observed run time** = `run_median_s`.
- Both appear next to the capacity change in plain words.

### 4.14 Parameters

`backend/app/params.toml` holds `version` (`dragonfly-ci-v1`, …), the defaults below, and `min_valid_cycles = 20`, which is fixed.

| Param | Default | Tuning grid |
| --- | --- | --- |
| `k` | 0.5 | 0.25, 0.5, 1.0 |
| `U` | 4 | 3, 4 |
| `h_w` | 3 | 2, 3, 4 |
| `h_i` | 6 | 5, 6, 8 |
| `W` (baseline days) | 60 | 45, 60, 90 |
| `G` (guard days) | 14 | 7, 14 |

That makes 324 combinations. The silence and high-level rules are fixed, not tuned, so they cannot be fitted to their own gates.

### 4.15 Benchmarks, all on identical cases

| Name | What it is |
| --- | --- |
| A, simple rule | `INVESTIGATE` when daily median run time > 1.5× its trailing median (same `W`, `G`); `WATCH` > 1.25×. No QC, no persistence, no siblings. |
| B, physics only | `z` on the capacity index: `WATCH` if `z < −3`, `INVESTIGATE` if `z < −5`. Single day, all cycles, no siblings. |
| C, Dragonfly | Everything in §4 |
| C − persistence | C with CUSUM replaced by a single-day `u < −5` / `u < −3` threshold |
| C − inhibition | C with `c_d = 0` |
| C − quality | C with every day treated as `SUFFICIENT` |

No ChatGPT head-to-head is run. A is labeled "simple rules", never "ChatGPT".

## 5. The situational experiment

### 5.1 The two locked incident scenarios (David, PR #3, v1)

The scenario files are the source of truth for every incident parameter. This section only summarizes them. Their schema is enforced by `backend/tests/test_scenarios.py`: every fact carries `{value, status: VERIFIED|UNVERIFIED, confidence: 0–100, source}`, and each rain file is pinned by sha256. No single mechanism reached the 80% bar, so each scenario carries two variants. **Both variants are evaluated and shown;** variant A is primary.

| Scenario id | Variant A (primary) | Variant B | Stand-in | Outcome to reproduce |
| --- | --- | --- | --- | --- |
| `bloomington_morningside_2024_04_11` | Progressive impeller ragging or clog. 6-day accelerating precursor; duty pump 60% degraded 24 h before failure; failure 2024-04-11T07:00Z. `PREDICTABLE_DAYS_AHEAD`, confidence 40. | Sudden pump, motor or control trip under storm load, no precursor. `DETECTABLE_AT_ONSET`, confidence 40. | 44371 | 14,310 gal ±20%; outage 145 min |
| `fishers_bowline_2009_01_20` | Power loss took down the controller; its backup battery was dead, so pumps, alarm and telemetry went silent at 2009-01-20T10:30Z. `DETECTABLE_AT_ONSET`, confidence 70. Target: `SOURCE_OFFLINE` within 5 min. | Controller or PLC fault with comms up: pumps stop while level rises. `DETECTABLE_AT_ONSET`, confidence 20. | 45385 | 25,000 gal ±20%; outage 530 min; discovery 180 min after failure |

**What these benchmarks can and cannot show** (locked wording for the README, Devpost and the demo):

- **They are record-anchored what-ifs, not reconstructions.** Date, rainfall, volume and the failure class come from the record. The mechanism, precursor and hydraulics are labeled assumptions (confidence 20–70). No pre-failure telemetry from either Indiana station exists.
- **G7 is a consistency check, not evidence.** `outage_duration_min` was derived from the reported volume, so reproducing the volume shows that the simulator and the scenario agree. Say "consistent with", never "validated against".
- **Morningside A is reported as a sweep, not one point.** Run `capacity_loss` with ramp 3, 6, 10 and 14 days, crossed with loss at 24 h before failure of 40%, 60% and 80%, all on the same analog. Report "caught before the trip if the precursor lasts at least N days". The 6-day point is one cell of that table.
- **Fishers' gallons saved depend on the 180-minute discovery assumption.** The card shows the result at 60, 180 and 360 min.
- **The headline accuracy claim comes only from the F1 family test tier (§6.7).** The Indiana cases illustrate it; they are never used to tune.

- `scenario_id` values in the API and MCP are exactly the file ids above, with a variant suffix: `bloomington_morningside_2024_04_11:A`, `:B`, and the same for Fishers.
- **Storm-readiness forecast:** David adds `fixtures/scenarios/forecast/bloomington_morningside_2024_04_11.json` from the Open-Meteo previous-runs API by 13:45, pinned by sha256 in a new `[conditions]` key (scenario v1 is otherwise unchanged). Archived forecasts do not reach 2009, so Fishers has no storm outlook.

### 5.2 Fault injection on real event streams

`backend/app/inject.py` transforms real station data. Every transform returns `(stream, truth)`, and `truth` goes only to the evaluator and the retrospective panel (§5.8).

| Transform | What it does |
| --- | --- |
| `capacity_loss(pump, onset, failure, loss, shape)` | For each cycle of the pump in the window, infer inflow `I = 3600/fill`, set `CI' = CI·(1 − loss(t))` with `loss(t) = loss·frac^p` (p = 1 linear, 2 accelerating), and recompute `run' = 3600/(CI' − I)`, capped at 3,600 s. All later station events shift by the added seconds. After `failure` the pump has no runs; its cycles are reassigned to the sibling with the sibling's own CI. This keeps the real noise and rain response. |
| `transient(pump, day, loss)` | `capacity_loss` for one day only |
| `station_shift(onset, factor)` | Every pump's CI × factor from onset (a setpoint change) |
| `duty_swap(pump, onset, days, share)` | Relabels cycles so the pump takes `share` of them |
| `outage(start, hours)` | Deletes all events and level rows in the window |
| `sensor_fault(kind)` | One of: level flatline 12 h, level dropout 6 h, negative level spikes, 5% duplicated run/stop rows, repeated starts |

In injected windows the level series stays real. The evidence notes "level is real and unmodified; the injected fault changes pump timing only."

### 5.3 Rain analog for the Indiana scenarios

- **Choosing the window:** for each Indiana scenario, pick the Wessex window at the stand-in station that minimizes the sum of squared differences between Indiana daily rain and Wessex daily rain (mm) over the 7 days before failure. The search is limited to the same calendar month ±1, so the season matches. The locked replay searches 2023; dev variants sample from the 10 best 2022 matches using the seed.
- **Time shift:** the analog is shifted by whole days so the failure lands on the record's date. That keeps daily patterns; weekdays may differ, and the evidence says so.
- **What the screen shows:** Indiana rainfall (Open-Meteo, actual). Inflow comes from the analog's real response. The evidence names both.

### 5.4 Outcome simulator

`backend/app/outcome.py` is a wet-well mass balance in gallons, used only to compute overflow volume and the scenario's level trace. Every physical number comes from the scenario file.

- **Step:** 15 s, with event times linearly interpolated.
- **Wet well:** usable storage is `wet_well_usable_storage_gal`; overflow is everything above it.
- **Pumps:** `pump_capacity_gpm_each`. The duty pump runs first; the standby joins when the duty pump alone cannot keep the level falling.
- **Inflow (gpm):** the analog's inferred inflow, scaled so its median dry-day value equals `dry_weather_inflow_gpm`. The same scale factor applies in storms.
- **Pump capacity over time:** capacity × `(1 − loss(t))` following the variant's precursor, 0 from `failure_timestamp_utc` until pumping is restored.
- **No-warning run:** pumping is restored `outage_duration_min` after failure. G7 checks this run against `overflow_volume_gal` within `overflow_volume_tolerance_pct`.
- **Fixing a miss:** David may change only the inflow assumptions or storage, and only as a new scenario version before 14:30.
- **Level trace:** mapped onto the stand-in station's real level scale. Pump-off maps to its median level at pump stop; usable-storage-full maps to its trailing P99.9. The trace feeds `HIGH_LEVEL` and the chart, labeled SIMULATED.
- **Outputs:** overflow start, duration and gallons.

### 5.5 Response policy (the counterfactual)

**Rule:** with Dragonfly, only the time until someone is told changes. Everything after that takes exactly as long as in the scenario. That makes the comparison like for like, with no invented crew speed.

| Case | With Dragonfly | Without |
| --- | --- | --- |
| Precursor variant (Morningside A) | A planned repair finishes R hours after the first `INVESTIGATE`, with R = 24, 48 or 96 h (headline: 48). If it finishes before failure, the failure does not occur and overflow is 0. If not, the outcome equals the no-warning run (conservative). A `WATCH` alone dispatches nobody. | The scenario's no-warning run |
| Onset variants (Morningside B, Fishers A and B) | Notification at the first `SOURCE_OFFLINE` or `HIGH_LEVEL`. Pumping is restored at notification + (`outage_duration_min` − `discovery_delay_min`). Morningside B has no published discovery delay, so it assumes the station alarm worked; Dragonfly then gains nothing, and the card says so. | Notification at `discovery_delay_min`; pumping restored at `outage_duration_min` |

The output is gallons with and without Dragonfly for each variant, with every assumption listed next to the number.

### 5.6 Synthetic families

Each family has dev seeds `0..n−1` (2022 windows) and test seeds `1000..1000+n−1` (2023 windows). Every case uses a random station and a 120-day window, generated deterministically from the seed with `numpy.random.default_rng(seed)`.

| Family | v1 name | Transform and ranges | Dev / test cases |
| --- | --- | --- | --- |
| F1 capacity loss | S1 | `capacity_loss`: loss U(0.10, 0.50), ramp U(3, 30) days, shape 50/50, failure in the last 30 days | 200 / 200 |
| F2 storm control | S2 | No fault; window centered on one of the 30 wettest station-days | 30 / 30 |
| F3 duty swap | S3 | `duty_swap`: share U(0.7, 0.9) for 30 days | 30 / 30 |
| F4 transient | S5 | `transient`: loss U(0.3, 0.5) | 30 / 30 |
| F5 outage | S6 | `outage`: U(2, 12) h | 30 / 30 |
| F6 sensor fault | S4 | `sensor_fault`: kinds rotate by seed | 30 / 30 |
| F7 station shift | new | `station_shift`: factor U(0.75, 0.85) | 30 / 30 |

**Case ids:** `<scenario_id>:<A|B>` for incidents and `<family>-<seed>` for families (for example `F1-1003`). `scenario_id` in the API is the same string. The Lab offers fixed test seeds through `/api/scenarios`: the first test seed of F2, F5 and F6 and the first F4 test seed with loss ≥0.4.

### 5.7 Real proxy events

`backend/scripts/proxy_events.py` finds, at the three stations, every episode where a pump has 0 runs for at least 2 days while a sibling runs. These are "pump out of service" proxies: real but unlabeled. Each episode goes to the tier of its year. The 44371 June 2022 episode is therefore dev data, and we say so whenever we show it.

### 5.8 Ground-truth isolation

- `truth` objects live only in `inject.py` output and in `replay_case`.
- `features.py`, `detect.py` and `assess_station` never receive them.
- `test_truth_isolation` checks this by import inspection.
- A scenario id selects input data, never an outcome. `test_scenario_blind` gives two ids identical inputs and asserts identical outputs.

## 6. Evaluation and refinement

### 6.1 Tiers

| Tier | Contents | Use |
| --- | --- | --- |
| Dev | 2022 real replay of 3 stations, dev seeds of F1–F7, dev variants of both Indiana scenarios, 2022 proxy events | Tune freely |
| Test | 2023 real replay, test seeds, the two exact locked Indiana replays, 2023 proxy events | Score once per frozen version. Never tune on it. |

### 6.2 Metrics (every one reported with its denominator)

- **F1 recall:** share of cases with pump `INVESTIGATE` on the injected pump after onset and before failure, in bins of loss (10–20, 20–30, 30–40, 40–50%) × ramp (3–7, 7–14, 14–21, 21–30 days). Lead time is failure minus the end of the first `INVESTIGATE` day, as median and P10, in days. The same is reported for `WATCH`.
- **False escalation:** share of F2, F3, F4 and F7 cases with any pump `INVESTIGATE`.
- **F5:** minutes from silence onset to `SOURCE_OFFLINE`.
- **F6:** share of cases raising the documented flag, and the count of `SUFFICIENT` days computed on a corrupted channel.
- **Real replay burden:** pump `INVESTIGATE` incidents and `WATCH` incidents per pump per 180 days, and the `INSUFFICIENT_EVIDENCE` share.
- **Proxy events:** share of out-of-service episodes preceded within 14 days by `WATCH` or `INVESTIGATE`, and share of `INVESTIGATE` incidents followed by an out-of-service episode within 30 days. These are called "proxy", never precision or recall.
- **Indiana:** class match, lead time, gallons with and without Dragonfly at each response time.
- **Everything above** for A, B, C and the three ablations.

### 6.3 Gates

A version cannot freeze unless every gate passes. Gates live in `backend/app/gates.toml`.

| Gate | Requirement |
| --- | --- |
| G1 | F5: 100% reach `SOURCE_OFFLINE` within 10 min (all three stations have 1-minute level), and no pump `INVESTIGATE` is raised during the outage. Fishers A is scored against its 5-minute target and reported, not gated. |
| G2 | F6: 100% raise the documented flag; 0 `SUFFICIENT` days on a corrupted channel |
| G3 | `test_no_lookahead` and `test_determinism` pass. No-lookahead: deleting all data after `as_of` changes nothing. Determinism: two full runs give byte-identical reports apart from the timestamp. |
| G4 | `HIGH_LEVEL` appears in the safety strip on 100% of the days its rule fires. A unit test proves no inhibition path touches it. |
| G5 | F2, F3, F4 and F7: false escalation ≤2% in each family |
| G6 | 2022 real replay: ≤1.0 pump `INVESTIGATE` incidents per pump per 180 days |
| G7 | Each locked Indiana scenario's no-warning simulation reproduces the record's gallons within ±20% |

### 6.4 Objective and tuning

- **Maximize** F1 dev recall on cases with loss ≥20% and ramp ≥7 days, subject to G1–G7.
- **Tie-breaks:** higher median lead time, then fewer real dev `WATCH` incidents.
- **Two commands:**
  - `make tune` runs all 324 combinations in parallel on cached dev cases and writes `reports/dev/grid.csv`. It runs at most once per version.
  - `make eval-dev` runs the current params in about a minute.

### 6.5 The refinement loop

This is the "keep refining against the simulation" loop, with the gaming guards built in.

1. Run `make eval-dev` and read `reports/dev/summary.json`. The command's output is the oracle, never an agent's claim.
2. Put every F1 miss and every false escalation in one bucket: `too_small`, `too_slow`, `few_cycles`, `overlap_days`, `inhibition_cancelled`, `baseline_contaminated` or `qc`.
3. Change **one** thing: one parameter value or one rule.
4. Rerun `make eval-dev`. Keep the change only if the objective rises and every gate holds; otherwise revert.
5. Log one row in `reports/decisions.md`: what changed, which bucket, and dev numbers before and after.
6. **Cap:** 6 iterations per version. Stop early after 2 iterations that each improve by less than 1 point.
7. **Freeze:** bump `version` in `params.toml` and open a PR, which needs code-owner approval (§11.3). Then run `make eval-test` **once** and append the result to `reports/test_runs.jsonl`. That file is never edited or deleted.
8. **Freezes today:** at most 3 (v1 at 15:15, v2 at 16:00, v3 at 16:20). The UI shows the latest frozen test result and how many test runs exist.

Fixing the injector or simulator for realism is allowed only before G7 passes for the first time. After that, the scenarios are frozen.

### 6.6 Reports

`make eval` writes the following.

- **`reports/evaluation.json`:** model version, code version, manifest hash, scenario hashes, params, metrics per tier, family, benchmark and ablation, gates, and caveats.
- **`reports/evaluation.md`:** the same content, rendered.
- **`reports/data_quality.json`:** the §3.5 counts.
- **`reports/test_runs.jsonl`:** the append-only test results (§6.5).

### 6.7 Claims

**Allowed**, filled only from reports:

> "On {n} held-out synthetic capacity-loss injections into real 2023 Wessex telemetry (≥20% loss over ≥7 days), Dragonfly raised INVESTIGATE before the pump trip in {x}% of cases, a median {y} days ahead. On the real 2023 replay it raised {z} INVESTIGATE incidents per pump per 6 months. {a} of {b} real pump-out-of-service episodes were preceded by a warning."

> "In a simulation of the Morningside 2024 equipment failure (mechanism assumed: {m}, confidence {c}), the first INVESTIGATE came {L} days before the simulated trip. With a 48-hour response, simulated overflow falls from {V0} gal (calibrated to the 14,310 gal record) to {V1} gal."

**Forbidden:**

- any failure probability, "will fail" or "would have prevented";
- an accuracy figure without its denominator;
- calling quiet periods "true negatives";
- any ChatGPT comparison presented as a result;
- calling Morningside's mechanism known.

## 7. Contracts (`backend/app/contracts.py`, Pydantic v2)

```python
Status = Literal["NORMAL", "WATCH", "INVESTIGATE", "INSUFFICIENT_EVIDENCE", "SOURCE_OFFLINE"]
Quality = Literal["SUFFICIENT", "PARTIAL", "INSUFFICIENT", "SOURCE_OFFLINE"]
Origin = Literal["REAL_REPLAY", "SYNTHETIC_INJECTION", "SIMULATED_INCIDENT"]
FindingType = Literal["CAPACITY_DROP", "STATION_WIDE_CHANGE", "PUMP_NOT_RUNNING",
                      "SOURCE_SILENT", "HIGH_LEVEL", "SENSOR_FAULT"]
ErrorCode = Literal["UNKNOWN_STATION", "UNKNOWN_SCENARIO", "UNKNOWN_ALERT", "UNKNOWN_CASE",
                    "BAD_TIMESTAMP", "AS_OF_OUT_OF_RANGE"]

Provenance:      source_hash, scenario_hash | None, model_version, code_version, signal_ids: list[str]
PumpState:       pump_id, status, quality, ci_today | None, ci_baseline | None, capacity_change_pct | None,
                 cusum, valid_cycles, runs, run_median_s | None, expected_run_s | None
Finding:         alert_id, type, pump_id | None, status, priority: int (1 = highest), opened_on: date,
                 days_open, observed | None, expected | None, units, change_pct | None, summary,
                 possible_causes: list[str], inspection: list[str]
RainContext:     today_mm | None, last_72h_mm | None, source
StormOutlook:    issued_on, forecast_rain_48h_in, max_gust_48h_mph, storm_ahead: bool
StationAssessment: station_id, display_name, as_of_utc, origin, scenario_id | None, status, quality,
                 pumps: list[PumpState], queue: list[Finding], safety: list[Finding], rain: RainContext,
                 storm: StormOutlook | None, missing_evidence: list[str], explanation, recommended_action, provenance
TraceRow:        day, quality, valid_cycles, ci, base_median, base_mad, z, common, u, cusum, status
Transition:      on: date, from_status, to_status, reason
RawEvent:        ts, pump_id, state: Literal["ON", "OFF"], signal_id
WorkOrder:       title, station_id, pump_id | None, priority, requested_by = "Dragonfly draft - needs human review",
                 checks: list[str], evidence_alert_id, caveats: list[str]
Evidence:        alert_id, station_id, pump_id | None, origin, as_of_utc, finding: Finding, rain: RainContext,
                 quality_flags: list[str], supporting: list[str], contradictory: list[str], unavailable: list[str],
                 trace: list[TraceRow] (<= 90), transitions: list[Transition], raw_events: list[RawEvent] (<= 500, trigger day),
                 level: list[tuple[datetime, float]] (<= 1440), work_order: WorkOrder, provenance
TimelineDay:     day, station_status, pumps: list[{pump_id, status, ci, base_median, cusum}]
Outcome:         no_system_gal, with_system_gal, by_response_h: dict[int, float], assumptions: list[str]
ReplayResult:    case_id, origin, family, title, truth: dict, timeline: list[TimelineDay],
                 first_watch_at | None, first_investigate_at | None, failure_at | None, lead_time_h | None,
                 outcome: Outcome | None, benchmarks: dict[str, {first_investigate_at, lead_time_h, incidents}]
ToolError:       code: ErrorCode, message, allowed: list[str]
```

- **Versioning:** one version string, `model_version`, covers detector and policy because both live in `params.toml`. There is no separate `policy_version`.
- **`code_version`:** `git rev-parse --short HEAD` at server start, or `unknown`.

## 8. Runtime interfaces

### 8.1 Internal functions (the David ↔ Dhruv seam)

```python
# David, backend/app
data.load(station_id, scenario_id | None) -> StationData   # events, level, rain, manifest hash, scenario hash; truth kept apart
features.daily_table(events, level, rain, end_utc) -> DataFrame   # §4.2 columns, only data < end_utc
detect.run(daily, params) -> DataFrame       # adds base_median, base_mad, z, common, u, cusum, station_cusum, status, incident_id, transition_reason
detect.realtime(events, level, as_of, params) -> list[dict]   # SOURCE_SILENT, HIGH_LEVEL, SENSOR_FAULT
params.load() -> Params
inject.apply(stream, transforms, seed) -> (stream, truth)
outcome.simulate(inflow, capacities, spec) -> OutcomeRun
# Dhruv, backend/app
assess.assess_station(station_id, as_of_utc, scenario_id=None) -> StationAssessment
assess.get_evidence(alert_id, as_of_utc) -> Evidence
assess.replay_case(case_id) -> ReplayResult
assess.timeline(station_id, scenario_id, start, end) -> list[TimelineDay]
explain.explanation(...) / explain.work_order(...)   # deterministic templates, §10.5
```

`assess_station` truncates inputs at `as_of` **before** computing features. Results are cached with `functools.lru_cache` keyed on `(station, scenario, as_of day)`.

### 8.2 REST (`backend/api.py`, FastAPI, 127.0.0.1:8000)

| Method and path | Returns |
| --- | --- |
| `GET /api/health` | `{status, model_version, source_hash, code_version}` |
| `GET /api/stations?scenario_id=` | Stations with pumps, data range and origin |
| `GET /api/scenarios` | Locked scenarios and family test cases offered in the Lab |
| `GET /api/assess?station_id&as_of_utc&scenario_id=` | `StationAssessment` |
| `GET /api/evidence?alert_id&as_of_utc` | `Evidence` |
| `GET /api/timeline?station_id&scenario_id=&start&end` | `list[TimelineDay]` (one call drives the time scrubber) |
| `GET /api/replay?case_id` | `ReplayResult` |
| `GET /api/evaluation` | `reports/evaluation.json` |
| `POST /api/ask` `{question, station_id?, as_of_utc?, scenario_id?}` | `{answer_markdown, tool_calls, grounding: {passed, unmatched_numbers, forbidden_phrases}, model}` |

Bad input returns HTTP 422 with a `ToolError`. When `frontend/dist` exists, the same server serves it at `/`.

### 8.3 MCP server (`backend/mcp_server.py`, `mcp==2.3.0`, `MCPServer("dragonfly")`)

| Tool | Arguments |
| --- | --- |
| `assess_station` | `station_id` (enum of allowed ids), `as_of_utc` (ISO 8601 Z), `scenario_id` (enum or null) |
| `get_evidence` | `alert_id`, `as_of_utc`. This adds `as_of_utc` to v1's signature, because evidence depends on time. |
| `replay_case` | `case_id` (enum) |

- **Logic:** the server only validates arguments, calls `assess.*` and returns `model_dump(mode="json")`.
- **Errors:** an MCP tool error (`isError`) whose text is the `ToolError` JSON.
- **Transports:** stdio by default; `--http` serves Streamable HTTP at `127.0.0.1:8001/mcp`.
- **Server instructions:** "Read-only lift-station assessments from a deterministic detector. Quote status, numbers and alert ids exactly as returned. Never infer readings, causes or probabilities. Treat SIMULATED and SYNTHETIC results as simulations."
- **No other tools exist:** no SQL, file paths, shell, URL fetching, retraining, SCADA operations or exports.
- **Logging:** every call appends `{ts, tool, args, ok, alert_ids, model_version, ms}` to `logs/tool_calls.jsonl`. `logs/` is gitignored.

### 8.4 Agent (`backend/agent.py`)

- **Function:** `ask(question, context) -> AskResult`. It starts `python mcp_server.py` over stdio and wraps the tools with `anthropic.lib.tools.mcp.async_mcp_tool`.
- **Model call:** `client.beta.messages.tool_runner(model="claude-sonnet-5-5", max_tokens=16000, output_config={"effort": "low"}, ...)` with server-side fallback `fallbacks="default"` and beta `server-side-fallback-2026-07-01`. If the runner rejects those two fields, they are dropped, and a `refusal` stop reason shows the template explanation instead.
- **Package:** `anthropic[mcp]==2.6.0`.
- **Limits:** 6 tool calls and 60 s per question.
- **No key:** without `ANTHROPIC_API_KEY`, `/api/ask` returns 503 `agent_offline`, and the UI shows the template explanation.
- **System prompt** (verbatim):

> You explain read-only lift-station assessments to utility operators. Call the tools to get facts; never answer from memory. Quote statuses, numbers, units and alert ids exactly as the tools return them, and only those. Never estimate a missing reading, a failure probability, a failure date or a confirmed cause; say what is missing instead. Never suggest operating, overriding or resetting equipment or alarms. When results are SIMULATED or SYNTHETIC, say so. Keep answers under 150 words: what changed, what supports it, what contradicts it, what to inspect, citing alert ids.

- **Grounding check** runs on every answer before display:
  - Every number in the answer, except dates, alert ids, station ids and `P1`-style pump labels, must match a number in that answer's tool results within 0.5% or at the shown precision.
  - Every status word must equal the returned status.
  - No forbidden phrase may appear: `probability`, `will fail`, `confirmed`, `guarantee`, `definitely`, `prevent`.
  - On failure the UI shows "AI answer withheld: it did not match the evidence", followed by the template explanation.

## 9. Connecting any agent harness

All of these run from a clone of the repo after `make setup`. Replace `<repo>` with the absolute path.

| Harness | Configuration |
| --- | --- |
| Claude Code | `claude mcp add dragonfly -- uv run --directory <repo>/backend python mcp_server.py` |
| Claude Desktop | `{"mcpServers": {"dragonfly": {"command": "uv", "args": ["run", "--directory", "<repo>/backend", "python", "mcp_server.py"]}}}` |
| Cursor (`.cursor/mcp.json`) | The same `mcpServers` block |
| VS Code (`.vscode/mcp.json`) | `{"servers": {"dragonfly": {"type": "stdio", "command": "uv", "args": [ ...same... ]}}}` |
| Codex (`~/.codex/config.toml`) | `[mcp_servers.dragonfly]` with `command = "uv"` and `args = ["run", "--directory", "<repo>/backend", "python", "mcp_server.py"]` |
| Remote (claude.ai custom connector, ChatGPT developer-mode connector) | `make mcp-http` plus `make tunnel` gives `https://<random>.trycloudflare.com/mcp`. It is up only during judging and needs no auth, because it serves only public CC BY data and labeled simulations. Real utility deployments would need OAuth and an on-prem host; that is stated in the README. |

The README "Use it from your agent" section carries these configurations plus three example questions:

- "Which stations need attention as of 2023-03-01?"
- "Why is 44371 pump 1 flagged on 2022-06-03? Show the evidence."
- "Replay the Morningside scenario and tell me how early it warned."

## 10. User experience

### 10.1 Frame

- **Stack:** one page, Vite + React + TypeScript, with Recharts for charts.
- **Header:** the product name, then a data-origin badge that is always visible:
  - `REPLAY · Wessex Water telemetry 2022–2023 (CC BY) · not live`, or
  - `SIMULATION · <scenario title>`.
- **Time controls in the header:** the as-of clock (`As of 2024-04-09 00:00 UTC`), `◀ day`, `▶ play` (1 day per second), `day ▶` and a date picker.
- **Tabs:** **Incidents** (the default), **Stations** and **Reliability Lab**.

### 10.2 Incidents tab

There is one card per locked scenario. Each card shows:

- what happened (record facts with VERIFIED/UNVERIFIED chips and source links);
- what failed: both variants side by side, each with its confidence and a one-line reason, and an A/B switch that picks which variant to replay;
- the outcome (gallons, where it went, who or what was affected, verified only);
- what Dragonfly can do: `PREDICTABLE_DAYS_AHEAD` reads "Warning days ahead is possible"; `DETECTABLE_AT_ONSET` reads "Detects the moment it happens; cannot predict it".

**Replay as if Dragonfly was there** loads the scenario into Stations with the as-of 30 days before failure and starts play. After the replay, the card shows a timeline strip: first `WATCH`, first `INVESTIGATE`, failure (record date), lead time, and gallons with and without Dragonfly at 24, 48 and 96 h.

A **Reveal simulation ground truth** toggle shows the injected parameters.

### 10.3 Stations tab

- **Left column:** station tiles, each with:
  - the station name;
  - pump chips (`P1`, `P2`, …) with status text and an icon;
  - the last data timestamp;
  - evidence quality in words;
  - a storm-readiness line when available ("Storm ahead: 0.98 in forecast for Apr 11, issued Apr 9").
- **Right column, top:** the **Safety (SCADA-equivalent)** strip (`HIGH_LEVEL`, `SOURCE_SILENT`).
- **Right column, below:** the **Attention queue**, with priority, opened, station, pump, finding, days open, change %, and status. Under it, "Low priority (n)", collapsed.
- **Clicking a row** opens the evidence drawer: a 560 px right-hand slide-over, full screen under 768 px.

### 10.4 Evidence drawer (in this order)

1. Status, the template explanation and the inspection checklist.
2. Chart: daily capacity index vs the baseline band (median ± 3 MAD), with CUSUM and the `h_w`/`h_i` lines, and rain bars on a second axis.
3. Chart: observed vs expected run time per day.
4. The trigger day's raw pump on/off timeline and level trace, with signal ids and UTC times.
5. Quality: cycles used and excluded, by reason.
6. Supporting, contradictory and unavailable evidence.
7. Provenance: alert id, signal ids, source hash, model version, code version and origin.
8. Draft work order, with a Copy button.
9. **Ask Dragonfly**, the agent box with the grounding badge.

### 10.5 Reliability Lab

1. **"Why not just upload it to ChatGPT?":** one paragraph (§19), then the A / B / C table from `evaluation.json`: degradations caught, median lead, false escalations in storm, duty and transient cases, and real alerts per pump per 6 months, each with its denominator.
2. **Ablations:** a table of C and the three ablations.
3. **Recall heatmap:** loss × ramp for C.
4. **Live experiments**, each loading a test case through the same API:
   - **Storm test:** A fires, C stays quiet.
   - **Break the level sensor:** `SENSOR_FAULT` appears, and the safety check reads `UNKNOWN`.
   - **Cut the power:** `SOURCE_OFFLINE` appears within N minutes.
   - **One bad day:** `WATCH`, then quiet.
5. **"What the model cannot know"** (fixed text):
   - sudden power, controller or vandalism failures days ahead;
   - the physical cause;
   - VFD stations;
   - anything with no telemetry;
   - real alarm setpoints.
6. **Proxy events:** "Real pump outages preceded by a warning: a of b".

### 10.6 Visual and copy rules (ISA-101 style; Praneetha owns exact tokens)

**Visual**

- Grey background and panels, dark grey text.
- Color only for abnormal states:
  - amber + ▲ for `WATCH`;
  - red + ◆ for `INVESTIGATE` and safety;
  - quality problems in grey hatch plus words ("Not enough data", "Source offline").
- **No green anywhere.**
- Charts are greyscale: observed series dark grey, baseline band light grey, thresholds dashed.
- Tabular numerals.
- WCAG 2.1 AA: color is never the only cue, there is full keyboard navigation, and focus is visible.

**Copy**

- Plain words, with units always shown.
- Never "probability", "will fail" or "confirmed".
- Every simulated number is labeled.

**Explanation template** (`explain.py`):

> "{Station} {Pump}: {STATUS}. Pumping capacity is {change}% below this pump's normal for {n} days ({observed} vs {expected} well-volumes per hour; run time {run_obs} s vs {run_exp} s expected at today's inflow). Rain does not explain it: this measure stays steady in storms{, and the other pump is normal}. {missing evidence}. Check: {checklist}. This is not a confirmed diagnosis."

**Inspection checklists:**

| Finding | Checklist |
| --- | --- |
| `CAPACITY_DROP` | Impeller clog or ragging; discharge valve fully open and check valve free; air binding; drawdown test for actual pump rate; motor current vs nameplate if available |
| `STATION_WIDE_CHANGE` | Confirm level setpoints unchanged; force-main restriction or air; common discharge valves |
| `PUMP_NOT_RUNNING` | Pump fail or overload alarm; HOA switch position |
| `SOURCE_SILENT` | Station power and RTU communications; dispatch if level is unknown in wet weather |
| `SENSOR_FAULT` | Level transducer; rely on floats and SCADA alarms until fixed |

## 11. Validation without humans in the loop

### 11.1 One oracle: `make verify`

CI runs `make verify` on every PR and every push to `main`. Agents use the same command locally. It runs:

1. `ruff check` and `ruff format --check`.
2. `pytest`:
   - unit tests per module;
   - contract tests;
   - `test_no_lookahead`, `test_determinism`, `test_truth_isolation` and `test_scenario_blind`;
   - `test_ci_rain_invariance`: on 44371 2022, the wet/dry CI ratio is within 0.95–1.05;
   - in-process MCP tests with `mcp.Client(server)`;
   - API tests with FastAPI's `TestClient`.
3. `make eval-smoke`: 14 fixed cases (2 per family), asserting G1–G5.
4. `npm run build` (tsc + vite).
5. `make mcp-smoke`:
   - `npx --yes @modelcontextprotocol/inspector@2.12.0 --cli <stdio command> --method tools/list`;
   - one `tools/call` of `assess_station`;
   - exit code must be 0.
6. `make e2e`: Playwright (chromium) against `make serve`, plus `@axe-core/playwright` with WCAG 2.1 A/AA tags and zero violations. The specs:
   - the origin badge is visible;
   - the Morningside replay shows `INVESTIGATE` before the failure marker;
   - the drawer shows `model_version` and the source hash;
   - Lab numbers equal `/api/evaluation`;
   - the broken sensor shows `SENSOR_FAULT`;
   - with the agent offline, the template still renders.

   Screenshots of the four screens are uploaded as CI artifacts. There are no pixel-diff baselines.

### 11.2 The other checks

| Command | When it runs | What it checks |
| --- | --- | --- |
| `make agent-eval` | In CI when the secret exists and `agent.py`, `mcp_server.py`, `contracts.py` or `explain.py` changed. Also locally. | 20 fixed questions in `backend/tests/agent_eval.toml`. Gate: 20/20 pass the grounding check. Advisory: a `claude-haiku-5-5` judge answers 3 yes/no/unknown questions per answer (claims a confirmed cause? suggests operating equipment? drops a missing-evidence caveat?). The fix loop never sees the judge's rubric text. |
| `make eval` | Local, at freeze | Full evaluation (§6) |

### 11.3 Anti-gaming guard

`.github/CODEOWNERS` assigns `@Iguta @dhruvbangera` to these paths. A change to any of them needs approval from a code owner who is not the author.

- `ARCHITECTURE.md`, `AGENTS.md`, `CLAUDE.md`, `.github/`
- `fixtures/scenarios/`, `fixtures/wessex/`
- `backend/app/params.toml`, `backend/app/gates.toml`
- `backend/tests/agent_eval.toml`, `backend/tests/test_gates.py`

**David enables by 13:00** (admin only): branch protection on `main` (PR required, status check `verify` required, code-owner review required, no force push), "Allow auto-merge", and the `ANTHROPIC_API_KEY` Actions secret.

### 11.4 Agent review and auto-fix (`anthropics/claude-code-action@v1`)

| Workflow | Trigger | Limits |
| --- | --- | --- |
| `review.yml` | Same-repo PRs, opened or synchronized | Inline review comments, advisory. `--max-turns 8 --max-budget-usd 1`. |
| `autofix.yml` | `workflow_run` of `CI` failing on a PR (from the action's `ci-failure-auto-fix` example) | At most 2 attempts per PR; branch prefix `claude-auto-fix-ci-`; `--max-budget-usd 3`. It cannot merge a change to protected paths, because §11.3 blocks it. |

When the secret is missing, both workflows exit 0 with a notice. The local loop (§12) still works.

### 11.5 Merging

- Every PR author's agent runs `gh pr merge --auto --squash`.
- A PR merges itself when `verify` passes, plus code-owner approval for protected paths.
- Humans approve only protected-path changes and `decision-change` PRs.

## 12. Agent board automation

`tools/board watch` (Dhruv, by 13:30) turns a board tag into a headless agent run.

**Setup per teammate:**

1. Run `gh auth login`.
2. Pull `main` and run `make setup`.
3. Leave `tools/board watch` running in a spare terminal. Codex users run `BOARD_AGENT=codex tools/board watch`.

**What it does:**

- **Polling:** checks every 30 s and acts on comments that tag you. Only these logins count: `Iguta`, `praneetha1795`, `dhruvbangera`.
- **Hops:** acts only when the comment's hop counter is below 3. Each auto-reply carries `hop:N`. At 3 it replies "hop limit, needs a human" and stops.
- **One job at a time.** For each:
  1. `git worktree add ../wa-board-<comment_id> -b board/<comment_id> origin/main`.
  2. Inside it, run the agent. The agent edits files and runs `make` targets only; it has no git or gh access.
     - Claude: `claude -p "$PROMPT" --permission-mode dontAsk --allowedTools Read Edit Write Glob Grep "Bash(make *)" "Bash(uv *)" "Bash(npm *)" "Bash(npx *)" --max-budget-usd 5 --output-format text`
     - Codex: `codex exec --sandbox workspace-write -o .board-result.md "$PROMPT"`
     - Wall-clock limit: 20 min.
  3. The watcher, not the agent, then decides:
     - **Diff is empty:** post the agent's reply text.
     - **`make verify` passes:** commit, push, `gh pr create --label stream:<owner stream>`, `gh pr merge --auto --squash`, then reply on the board with the PR link and `hop:N+1`.
     - **`make verify` fails:** open a draft PR and reply with the failing step.
  4. Remove the worktree. Write a log to `logs/board/<comment_id>.log`.

**`$PROMPT`** (verbatim, with the comment URL and body appended):

> You were tagged on the team board. Read AGENTS.md and ARCHITECTURE.md first. Do the request below only inside your human's paths (AGENTS.md). Run `make verify` before you finish. Do not commit, push or post; the watcher does that. If the request is outside your paths, unclear, or needs a decision ARCHITECTURE.md does not make, change nothing and reply with exactly what you need and from whom. End with a summary of at most 5 lines.

The existing `tools/board wait` stays, for interactive sessions.

## 13. Repository layout and ownership

This updates AGENTS.md in the same PR.

| Owner | Paths |
| --- | --- |
| David (`stream:data`) | `backend/app/{data,quality,features,detect,inject,outcome,scenarios}.py`, `backend/app/params.toml`, `backend/app/gates.toml`, `backend/scripts/`, `fixtures/`, `reports/` |
| Dhruv (`stream:api`) | `backend/app/{contracts,assess,explain}.py`, `backend/{api,mcp_server,agent}.py`, `backend/pyproject.toml`, `backend/uv.lock`, `Makefile`, `e2e/`, `.github/`, `tools/`, `docs/`, `fixtures/ui/` (sample payloads for the UI) |
| Praneetha (`stream:ui`) | `frontend/` |

**Tests:** `backend/tests/test_<module>.py` belongs to the module's owner. `agent_eval.toml` belongs to Dhruv; `test_gates.py` to David.

## 14. Commands, environment and versions

| Command | Does |
| --- | --- |
| `make setup` | `uv sync` in `backend/`, `npm ci` in `frontend/` and `e2e/`, `npx playwright install chromium` |
| `make fixtures` | Export from `$WESSEX_DIR` (David only) |
| `make test` | ruff and pytest |
| `make verify` | §11.1 |
| `make eval-smoke`, `make eval-dev`, `make tune`, `make eval-test`, `make eval` | §6 |
| `make serve` | Build the frontend, run the API and UI on `127.0.0.1:8000` |
| `make mcp` / `make mcp-http` | MCP over stdio, or HTTP on `127.0.0.1:8001/mcp` |
| `make e2e`, `make mcp-smoke`, `make agent-eval` | §11 |
| `make tunnel` | `cloudflared tunnel --url http://127.0.0.1:8001` |

- **Environment variables:** `WESSEX_DIR` (fixture export only) and `ANTHROPIC_API_KEY` (agent, optional). Nothing else.
- **Backend versions:** Python 3.12 and uv. Pinned in `uv.lock`: pandas, numpy, pyarrow, pydantic 2, fastapi, uvicorn, httpx, `mcp==2.3.0`, `anthropic[mcp]==2.6.0`, pytest, anyio, ruff. No scikit-learn and no scipy.
- **Frontend versions:** Node 22. react, react-dom, recharts, vite, typescript. `e2e/`: `@playwright/test`, `@axe-core/playwright`.

## 15. Schedule (ET)

| By | Milestone | Owner |
| --- | --- | --- |
| 12:30 | This PR merged | Dhruv; David and Praneetha review |
| 12:45 | Two scenario TOMLs locked (done: PR #3). Forecast JSON follows by 13:45. | David |
| 13:15 | `contracts.py`, `pyproject`, `Makefile`, CI with ruff and pytest, sample payloads in `fixtures/ui/` | Dhruv |
| 13:30 | `tools/board watch`; branch protection and secret | Dhruv; David |
| 13:45 | Fixtures exported, QC, daily table, `test_ci_rain_invariance` | David |
| 14:30 | Detector; real replay end to end through `assess`, REST and MCP; UI on sample payloads | David; Dhruv; Praneetha |
| 15:00 | `inject.py`, families, `outcome.py`, G7 passing; agent and grounding; UI on the live API | David; Dhruv; Praneetha |
| 15:15 | Freeze v1: `make tune`, then `make eval-test`, then reports | David |
| 15:45 | Indiana replays and the Lab with real numbers in the UI; e2e and axe green | Praneetha; Dhruv |
| 16:20 | Last freeze; README run steps and "Use it from your agent"; Devpost draft | All |
| 16:30 | Code freeze. Rehearse the demo, start the tunnel, submit by 16:55. | All |

Lunch is 12:30–13:00 per PLAN.md. The board watchers keep agents working through it.

**Cut rules, closed in advance:**

- If the 14:30 milestone slips past 15:00: drop F7, storm readiness and `agent-eval` in CI, and keep G1–G6.
- If the 15:00 milestone slips past 15:45: Indiana replays show detection timing only, with no gallons, and the card says so.

Provenance, no-lookahead, quality handling and honest labels are never cut.

## 16. Out of scope (closed)

- Ignition.
- Video, except a 60–90 s screen recording at 16:35 if the Devpost form requires one.
- Gradient boosting or neural models.
- Flow and pressure.
- Level-based drawdown.
- Live connectors, notifications, acknowledge/resolve, accounts and auth beyond localhost.
- Hosted deployment.
- Multi-agent orchestration, vector databases.
- A ChatGPT head-to-head experiment (named as future work).
- Fictional station names.
- VFD stations.

## 17. Decision owners

| Area | Owner |
| --- | --- |
| Data, QC, model, injection, outcome simulator, scenarios, evaluation, gates | David |
| Contracts, assess, explanations, REST, MCP, agent, CI, validation, board automation, this file's editing | Dhruv |
| Visual design tokens, layout details within §10 | Praneetha |

## 18. Risks and their fixed responses

| Risk | Response |
| --- | --- |
| G7 cannot reach ±20% | David changes only the inflow assumptions or storage, as a new scenario version, before 14:30. After that, publish the gap. |
| Morningside variant A is not detected before failure | Show it. That is exactly what variant B's tie at 40% warns about. Never tune on the exact scenario. |
| A test result disappoints | Publish it. No tuning on test. At most 3 freezes. |
| No API key | Template explanations in the UI. The agent demo runs in Claude Code on Dhruv's laptop through MCP, using his own login. |
| No Actions secret | Cloud review and fix are skipped; local loop and `make verify` remain |
| Frontend late | Demo with Claude Code plus MCP and `reports/evaluation.md` |
| Tunnel fails | Local-only demo |
| Fixtures over 40 MB | Drop 2022-01-01 to 2022-01-15, which the warm-up does not need |

## 19. Demo (5 minutes) and pitch

1. **0:00–0:40, Incidents tab.** Morningside: 14,310 gal of sewage during an April storm. Fishers: 25,000 gal after a power failure took down a controller whose backup battery was dead, so nobody was alerted; the same manhole later drew a state fine. Say what the records do and do not tell us, and that each has two possible mechanisms.
2. **0:40–1:10, the mentor question.** "Could ChatGPT analyze this? Yes. What an operator trusts the next morning is a pipeline that measures pump capacity directly, ignores rain by physics, checks its own data, and says when it doesn't know."
3. **1:10–2:30, replay Morningside.** Watch the capacity index fall days before the storm. The storm-ahead line raises its priority. `INVESTIGATE` lands {L} days before the simulated trip. Read the gallons with and without Dragonfly.
4. **2:30–3:15, open the evidence.** Raw pump timestamps, the baseline band, why the rain doesn't explain it, the sibling pump normal, the provenance hash, the draft work order.
5. **3:15–3:50, attack it in the Lab.** Storm test: the simple rule fires, Dragonfly stays quiet. Break the level sensor: Dragonfly says `UNKNOWN` instead of bluffing. Cut the power: `SOURCE_OFFLINE` in minutes, which is the Fishers lesson.
6. **3:50–4:30, real data and engineering.** The 44371 pump caught 10 days before a real outage (dev data, labeled). The test-set numbers with denominators. CI with green `verify`, the gates, the CODEOWNERS-locked benchmark, and an agent asking our MCP server from Claude Code.
7. **4:30–5:00, vision.** It sits above any SCADA, read-only, and needs only on/off timestamps. Next step: a pilot with real maintenance logs to measure true precision.

**Pitch line:** "Not a chatbot that guesses what's wrong. A pipeline that measures each pump's capacity from data you already log, and knows when the evidence is strong enough to interrupt an operator."
