# Dragonfly AI — Claude Code Master Handoff

> **Role:** You are the technical lead, senior MLOps engineer, time-series scientist, OT-security reviewer, and pragmatic hackathon builder working inside the existing `Iguta/wastewater-analytics` repository. Build a **demonstrably reliable, read-only wastewater lift-station early-warning prototype**. The central challenge is not to produce an impressive prediction. It is to prove why this repeatable, evidence-gated system deserves more operational trust than a one-off ChatGPT analysis of a large data dump.
>
> **Priority order:** (1) working end-to-end inference service, (2) tested read-only MCP tool wrapper, (3) an agent that consumes structured results, (4) truthful/reproducible reliability evidence, (5) useful operator UX, (6) optional novelty/video. Never sacrifice inference correctness or safe abstention for an impressive conversation.
> **Canonical system boundary:** The trained model and deterministic evidence/alert policies compute the assessment. The **MCP server exposes** those assessments as typed, read-only tools. The **LLM agent consumes** tool results to summarize, answer questions and propose human-reviewed follow-up actions. The agent must never substitute its own prediction for the tested model.

## 0. First actions and decision authority

1. Read the repository's existing `README.md` and `PLAN.md` **before** changing anything. Their team roles, 9 AM–5 PM event window, source choices, and safe read-only scope are our working baseline. Do not overwrite the team's decisions without explicitly recording why.
2. Inventory the current code, branches, commits, dependencies, and data assets. Preserve work already underway; coordinate around each teammate's files. Do not claim an implementation exists solely because the planning docs describe it.
3. Locate the shared datasets and notebooks using the links below or the local paths the user provides. If the Drive link is inaccessible, work with whatever real files are accessible. **Do not silently fabricate source data**; only create clearly labeled synthetic scenarios. Report missing resources in a short status note, then continue productively.
4. Check available time and identify the **smallest demoable slice**. If little time remains, implement the fallback baseline, data-quality contracts, four synthetic scenarios, API/UI integration, and reproducible test report. Drop Ignition and all video work before cutting tests.
5. Use AI coding tools aggressively but inspect their output. Every significant defect found in AI-generated code should be recorded in a decisions/corrections log. The judging guide explicitly asks to show AI-assisted decisions and corrections.
6. Build only during the authorized hackathon period, and commit actual work throughout the day. Planning/data exploration completed before kickoff is acceptable under the provided rules; don't rewrite history or claim otherwise.

**Deliverable definition:** A judge can select a station and scenario, see observed versus expected pump behavior, see when an event became persistent enough to surface, inspect **raw → cleaned → features → model → policy → evidence → alert**, and challenge it with rain or sensor failure. It is live, locally reproducible, and honest about what it does not know.

## 1. The mentor's challenge: “Why not just upload all the data to ChatGPT?”

### Give the accurate answer, not a strawman

**ChatGPT with tools can absolutely analyze CSVs, train a reasonable model, and generate graphs.** Do not claim otherwise. The distinction is that an ad hoc assistant session is not, by itself, a continuously operating, versioned, data-quality-aware, safety-bounded, independently evaluated industrial monitoring service.

Our **testable value** is the engineered pipeline around the model:

| Question a skeptical judge asks | What our system demonstrably provides |
|---|---|
| “Where did the alert come from?” | Exact signal IDs, timestamps, data version/hash, transformations, feature values, model version, thresholds, decision state history, and evidence packet. |
| “Will it give the same answer tomorrow?” | Pinned dependencies, deterministic features, fixed model artifact, training/evaluation split, seed, fixtures, regression tests. |
| “Can it tell a storm from a damaged pump?” | Pump-specific, rain-conditioned expected-behavior baseline; negative-control storm tests; independent signal checks where actually available. |
| “Does it just alarm on every spike?” | Persistent-change tracking, deduplication, hysteresis, contextual suppression, alert-budget evaluation. |
| “What if the sensor is wrong, stale, or missing?” | Quality gates; explicit `INSUFFICIENT_EVIDENCE` or `SOURCE_OFFLINE`; never hallucinate missing readings. |
| “What does 80% risk mean?” | **We do not show an uncalibrated failure probability.** Show measured deviation, alert state, and evidence sufficiency. |
| “What if the prediction is wrong?” | Explicit limitations, alternate hypotheses, operator review, provenance, no actuator/control pathway, safe fallback to original alarms. |
| “Can this work without handing data to a cloud chatbot?” | Local deterministic feature/model inference; local/template explanations; read-only adapter design; ability to keep utility data inside its security boundary. |
| “Is it actually better?” | Frozen test scenarios, model ablations, measured alert burden and detection time. **Show the numbers even if they are not flattering.** |

**Judge pitch (20 seconds):**
> “A general AI can build a forecast from a spreadsheet. We built the infrastructure around that forecast that makes it usable in operations: data checks, pump-specific and rain-aware baselines, persistent evidence tracking, explicit uncertainty, a reproducible evaluation, and a read-only alert workflow. Here is one of our alerts; you can trace every number back to its source. Now turn off the rain model or break a sensor and watch the system respond safely.”

**One-line positioning:** “Not a chatbot that guesses what's wrong. An auditable decision pipeline that knows when the evidence is strong enough to interrupt an operator.”

**Avoid false claims:** ChatGPT is not inherently incapable of reproducibility, privacy, local deployment, ML training, or integration. Those are engineering requirements that we have deliberately implemented and verified, not exclusive powers of a custom model. Likewise, do not claim superiority to StormHarvester, iFactory, or OxMaint without a shared benchmark.

### Demonstrate the distinction, don't merely describe it

Have a `Why-not-ChatGPT?` / `Reliability proof` section in the UI or a prepared one-click sequence. Demonstrate **three matched approaches on the same input**, keeping dataset/window/decision timing fixed:

- **A. Fixed-threshold / simple summary:** a deterministic baseline analogous to simplistic data review. A simplistic LLM-generated rule is not a fair proxy for ChatGPT's full analytical capability; label this as *simple rules*, not “ChatGPT accuracy”.
- **B. Contextual expected-behavior model:** pump-specific baseline conditioned on rainfall and operating context.
- **C. Dragonfly evidence-gated selector:** model B + data quality, persistence, contextual inhibition, event deduplication and prioritized operator actions.

Additionally show an **ablation**: C with target-selection/persistence off versus on. If desired, show a separate **interactive LLM explanation** for a single fixed snapshot; keep its role distinct from the statistical model. **Never invent a rigorous head-to-head experiment against ChatGPT you did not actually conduct.**

If the team can conduct a fair assistant baseline, give a general-purpose assistant the same **timestamp-bounded** records and explicit objective, allow it computational tools, record its prompt/model/tool setup/cost and lock the output before seeing labels. Otherwise say that a formal general-AI baseline is future work.

## 2. Product thesis, buyer, and safe boundary

**Product:** Dragonfly AI, read-only intelligence layer for wastewater **lift stations**, initially for utility operators and maintenance planners. It consumes the telemetry utilities already collect; detects *abnormal operational behavior* rather than diagnosing unobserved root causes; filters obvious context noise; emits a ranked evidence-backed inspection queue and draft maintenance work orders.

**Users:** An operator needs “which station/pump, why now, how trustworthy, what should I check?” A maintenance planner needs “which sites deserve attention before the next storm and why?”

**Not building:** a PLC controller, SCADA replacement, full CMMS, guaranteed failure-date predictor, municipal live-data integration, or new proprietary sensor product. Nothing writes to a control system. Never suppress or override independent critical SCADA safety alarms.

**Novelty:** A **dragonfly small-target-motion-detector (STMD)-inspired** selection layer that suppresses distracting candidates and rewards coherent deterioration trajectories. It is a biomimetic *algorithmic design analogy*, not an accurate replica of a biological neural network or a new deep net unless trained and independently tested.

**Commercial claim to test later:** Existing monitoring systems show status and individual alarms; Dragonfly may improve the evidence-to-action workflow while sitting above vendor systems. StormHarvester already offers sophisticated wastewater alerting, so differentiate through **auditable uncertainty, local-first deployment, vendor-neutral adapter contracts, explicit abstention, and verified alert economics**. These are product hypotheses, not proven market exclusivity.

## 3. Sources: read and verify before engineering

### Canonical project resources

- Team repo: https://github.com/Iguta/wastewater-analytics
- Team planning files: `README.md`, `PLAN.md` in that repo
- David's dataset folder: https://drive.google.com/drive/folders/1x6gIb-EptRJB1q5HUdvWV4wzom5nesct
- Wessex telemetry exploration notebook: https://colab.research.google.com/drive/1jbtOWFJ2bj38W74FqdsBRbqEo_zdHmNr
- Bloomington overflow exploration notebook: https://colab.research.google.com/drive/1RPnH1W6hpVb9hyLlsvKKX60hOnVOUIGL
- Wessex official data description: https://marketplace.wessexwater.co.uk/dataset/rising-mains-telemetry-asset-and-rainfall-data
- Wessex official challenge: https://marketplace.wessexwater.co.uk/challenges/applying-machine-learning-at-rising-mains-and-sewage-pumping-stations
- Bloomington historical SSO records: https://data.bloomington.in.gov/Utilities-Water/Sanitary-Sewer-Overflows/kfaf-msfz
- Competitor products: https://stormharvester.com/case-studies/ ; https://ifactoryapp.com/industries/infrastructure-management/lift-station-pump-station-maintenance-ai-wet-well-monitoring ; https://oxmaint.com/industries/government/wastewater-lift-station-predictive-maintenance-system
- Optional data schema inspiration: https://github.com/smart-data-models/dataModel.WasteWater/tree/a554101634eea7dad438551b4e04099d9f6960fd
- Do not use as training reference: https://github.com/nitin19827/Smart-Swage-Management-System-Using-AI/tree/main/Smart%20Sewage%20Management%20System (predicts drinking-water *potability*, not lift-station faults).

### Preferred datasets and correct roles

**1. Wessex Water 2022–2023 station telemetry: MODEL DATA.** Use station-level pump ON/OFF events, wet-well levels, and site-linked rainfall. It contains 24 pumping stations and real burst events but publicly usable confirmed burst labels are not supplied. Therefore build **normal-behavior regression + anomaly detection**, not a supervised classifier with pretend field-failure labels.

The previously audited shared sample included:
- `site_43014_runstop.csv`: 193,205 records, two pump signals, duplicate timestamps/repeated-state events requiring cleansing; approximately 100-second median runs.
- `site_43014_level.csv`: 199,439 observations, typically five-minute cadence, including invalid negative readings. Cannot estimate individual ~100-second cycle drawdown reliably from five-minute level samples.
- `sps-local-rainfall-data.csv`: 420,480 hourly records across 24 stations for 2022–2023, useful for context.
- `rising-main-diameter-and-key-to-telemetry-signals.csv`: per-site signal dictionary and asset mapping.
- Other planned sites: 45497 (two balanced pumps), 45078 (three busy pumps), and 43014 (duty/standby skew). Verify availability and quality before using.

These are **previous audit observations on copies of the files, not permission to hardcode counts**. Re-run validation on the exact files actually loaded and record version/hash.

**2. City of Bloomington historical overflows: LOCAL PROBLEM EVIDENCE only.** Previously examined file `Sanitary_Sewer_Overflows_20261102.csv` had 1,101 entries with incomplete causes and volumes. It includes an April 11, 2024 Morningside Lift Station equipment-failure overflow (reported 14,310 gallons); validate the specific row against the original source before putting it on-screen. This is NOT a linked training label for UK telemetry or proof a predictor would have prevented that event.

**3. Rainfall:** UK station-matched Wessex rain is valid for UK telemetry modeling. Indiana weather archives may enrich the local incident narrative, **never combine Indiana rainfall with Wessex pump data in training**.

**4. Additional flow/pressure:** only if present and cleaned/aligned; treat as optional independent corroboration. Do not claim motor vibration, current, temperature or failure cause is measured when it is not.

### Mandatory data contract

Normalize to typed records with at minimum:
`station_id`, `pump_id`, `signal_id`, `observed_at_utc`, `value`, `units`, `source_file`, `source_hash`, `quality_flags`.

Data-quality checks must include timestamp parsing/timezones; duplicate rows; repeated start/start and stop/stop events; pump event pairing **within the same pump**, never across pumps; unmatched events; negative/out-of-range wet-well levels; stale/flatlined sensors; rain joins and temporal coverage; unavailable units; missing windows; enough clean cycles; correct train/test leakage boundaries. Preserve a full quality report rather than silently dropping everything. Do **not** forward-fill missing binary state changes and pretend they're measured transitions.

## 4. Exact modeling question and conservative answer

**Allowed question:** “For this pump at this station, is today's observed operating behavior unusual relative to its own expected behavior under recent rainfall, seasonality, and known operating context? Is there sustained, reliable evidence deserving inspection?”

**Disallowed answers:** “92% chance of pump failure tomorrow”; “this exact bearing is defective”; “we would have prevented the Bloomington incident”; “every quiet period is a verified true negative.” There are not enough verified field-failure labels for those statements.

### Features (build from available inputs, with proper as-of timestamps)

- Per-pump start/stop pairs, run duration, median/P90 runtime per window, starts per hour, total duty time, short/long cycles as *contextual features*, not universal defect rules.
- Per-pump prior-window deviations and duty rotation. Pump 1 working less than pump 2 is often normal; *within-pump change* is the important signal.
- Site-linked rain totals and lags for 1h/6h/24h/72h; relevant month/day/calendar effects. No future weather in a historical decision.
- Wet-well level trend on **time windows long enough for sensor cadence**; if resolution is inadequate, mark it unavailable.
- Optional pressure/flow confirmation if timestamps and units align with pump events.
- Source freshness, coverage, missingness and number of valid cycles as *evidence quality* features, not fictional physical telemetry.

### Mandatory baseline and preferred trained model

**Model 0 (must work):** A per-pump rolling median/MAD expected-behavior baseline, stratified by relevant rain/operating context when possible. Use a robust deviation score and persistent-change tracking. This is a technically respectable fallback and has no black-box excuses.

**Model 1 (recommended):** One small scikit-learn gradient-boosted regression model that predicts *expected log median runtime* for a pump and period, conditioned on rain, station/pump identity, season and strictly lagged historic features. Normalize residuals using scale calculated from train/validation data. **Do not train on target runtime or any full-window derived feature to predict itself.** If only end-of-day inference is supported, clearly label it retrospective/daily early warning, not a real-time per-minute forecast.

**Split:** Train on early 2022, tune/check on later 2022, freeze parameters, evaluate on held-out 2023. If 2022 is too sparse/shifted at a site, document the limitation rather than smoothing it away. In future test unseen-station generalization separately. Freeze thresholds before examining final test performance.

**Change detection:** EWMA or one-sided CUSUM on standardized residuals with explicit minimum evidence coverage, hysteresis and cooldown. Never call isolated high residuals “confirmed failure.”

### The Dragonfly selection layer

Implement **a small, visible algorithm**, not an unnecessary deep neural architecture:

1. **Local detectors:** identify candidate abnormal runtime, altered level behavior, cycle bursts, and sensor-integrity issues.
2. **Contextual inhibition:** down-rank candidates explained by heavy rain or a normal duty/standby change; do not suppress critical safety alarm conditions.
3. **Trajectory facilitation:** increase priority only when the abnormal pattern persists coherently over multiple observation windows; fixed and testable logic.
4. **Target tracking:** group repeat evidence about the same pump issue into one evolving incident with persistent ID and history.
5. **Competitive attention:** rank the action-worthy incidents; keep a transparent audit of low-priority events rather than hiding data.

Evidence status must be one of: `SUFFICIENT`, `PARTIAL`, `INSUFFICIENT`, `SOURCE_OFFLINE`. Operator state should distinguish `NORMAL`, `WATCH`, `INVESTIGATE`, `ACKNOWLEDGED`, `RESOLVED` and `UNKNOWN`. Severity ≠ anomaly score ≠ probability of failure. Explicitly expose contradictory evidence and unmeasured signals.

**Important scientific caveat:** Rain can coincide with genuine failures. Rain is a conditional explanatory variable, not an absolute excuse that turns off all alerts.

## 5. Trustworthiness: measurable, falsifiable acceptance criteria

Treat **a completed reliability test suite** as a core product feature. The judges should be able to click and observe test behavior, not just read claims.

### Required scenarios (deterministic, versioned, clearly marked synthetic when applicable)

| Scenario | Injection / negative control | Expected behavior |
|---|---|---|
| S1 Gradual pump degradation | On a fixed held-out real telemetry slice, progressively lengthen apparent pump run times and/or reduce credible relative pumping efficacy. Preserve event ordering and physical plausibility. | Sustained alert emerges before a declared **synthetic** failure boundary, if signal strength supports it; record detection lead time. |
| S2 Storm without mechanical fault | An untreated real rainy period and/or carefully labeled storm-load simulation. | Contextual baseline appropriately avoids *mechanical failure* over-escalation; existing high-wet-well safety conditions still surface. |
| S3 Duty/standby asymmetry | Two-pump site with skewed normal use (e.g., station 43014). | Does not flag skew alone as wear. |
| S4 Frozen, stale, missing, out-of-range level readings | Inject invalid/missing level channel, including prolonged flatline. | Evidence quality drops; abstain from any diagnosis requiring level corroboration; explain what is missing. |
| S5 Single transient spike | One isolated runtime anomaly followed by normal behavior. | Candidate logged, not repeatedly promoted as persistent imminent failure. |
| S6 Sudden power loss | Immediate total loss of pump telemetry/state. | Explicitly detect outage/data loss as a monitoring problem, **never claim days-ahead prediction**. |

Tests must derive output from the same real code path as production inference; **never branch on scenario name to create a predetermined status**. A scenario selector changes *input fixture data*, not predictions. For synthetic anomalies, keep immutable ground truth inaccessible to model/policy code. Reveal it only in evaluator and UI's clearly marked retrospective panel.

### Evaluation comparisons

**Benchmarks, all on identical replay windows:**
- A: fixed/simple thresholds (if defined and reasonable)
- B: rain-aware expected-runtime residual model
- C: B + evidence quality + temporal tracking + Dragonfly selection
- D: C with temporal selection/attention disabled (ablation)

Measure and publish:
- **Synthetic fault**: detected or missed, earliest alert timestamp, lead time relative to synthetic event boundary, precision/recall if sufficient controlled labeled scenarios exist.
- **Real, unlabeled replay**: number of distinct alerts, alert-hours per station-week, queue size, duplicate alerts collapsed, quality abstention rate. **Do not call unlabeled periods false negatives or true negatives.**
- **Storm negative controls**: count of mechanical alarms during storms, compared under equal evaluation conditions; inspect for mistaken suppression.
- **Data integrity**: invalid event detection rate on labeled corrupt fixtures; no unflagged use of bad signals; traceability coverage (% alerts with complete provenance).
- **Operational resilience**: reproducible restart/offline replay, safe behavior when model file absent, API response time if easy to measure.

**Success criteria to aspire to, not numbers to invent:** 100% of intentionally corrupted fixture fields trigger documented QC flags; 100% of alerts expose source/model provenance; no critical safety alarm suppression; scenario outcomes reproducible with a fixed seed; C meaningfully lowers redundant action alerts compared with a simpler baseline **without missing the injected slow degradation**. Report actual results, including any failures.

Generate `reports/evaluation.json` and `reports/evaluation.md` with dataset checksums, time split, model configuration, model version, thresholds, scenario parameters, metrics + denominators, and caveats. A single command should recreate the artifacts.

### Independent model review checks

- Verify raw data integrity **before** training; never train/test on the exact same temporal slice.
- Ensure per-pump run/stop pairing, timezones, calendar rain lag alignment, and day-boundary calculations are correct. Include adversarial fixture tests.
- Fit normalizers/imputers **only** on training data; never fit on held-out observations.
- Never leak injected fault labels or post-failure information into inputs/threshold tuning.
- Explain any station-specific variance, including unusual normal pump rotation.
- Compare actual-vs-expected on **honestly chosen** scales; graph time and available-data boundaries.
- Keep uncertainty separate from severity and absence of alert separate from guarantee of health.
- Avoid scientifically unsupported precision (e.g., probability of an exact fault without labels).

## 6. System design and implementation contract — MCP-first, simple and auditable

**Architectural goal:** train the small lift-station algorithm once, then expose it to a conversational agent through an MCP server. The MCP server is an **interface**, not the ML training algorithm and not the agent's reasoning engine. Do not dump all historical CSVs into the agent's context. Avoid a multi-agent architecture, vector database, orchestration framework or large workflow until measured need emerges.

```text
Wessex data / later: approved read-only historian
                  ↓
     parsing + quality checks + features
                  ↓
  trained deterministic model + policies
        (single local Python function)
                  ↓
           structured assessment
          ┌───────┴────────┐
          ↓                ↓
     MCP server       optional REST endpoint
   (read-only tools)      for charts / offline UI
          ↓                ↓
  one LLM agent       operator dashboard
          ↓                ↑
 summary / question answering / suggested inspection
           (grounded in evidence, human reviewed)
```

**Build order, mandatory:** (1) reliable `assess_station(station_id, as_of_utc, scenario_id=None)` standalone Python function, (2) schema + unit tests for output and abstention, (3) one MCP server exposing that same function, (4) an agent that successfully calls the MCP tool, (5) evidence inspector / reliability lab UI. Start with a saved model artifact and precomputed features if time is tight; a complex streaming runtime is unnecessary.

**One inference implementation, never two.** The MCP tool and any optional REST API import exactly the same `assess_station` core. Training remains offline; inference must not retrain on every query. Supply stable model version and source data hash in every response. Keep the demo functional without an LLM by rendering the deterministic assessment directly in the browser.

### Minimal MCP tools (three maximum for P0)

1. **`assess_station(station_id: str, as_of_utc: str, scenario_id: str | None = None)`** — deterministic structured assessment for one station and time, with pump health states, severity, evidence adequacy, rainfall context, and pointers to evidence. For a demo, `scenario_id` is a strict allowlist; invalid values fail closed. Return `INSUFFICIENT_EVIDENCE` instead of a diagnosis when inputs are unreliable.
2. **`get_evidence(alert_id: str)`** — inspect the exact inputs, transformed features, model artifact hash/version, conditions, timing, detector/policy decisions, supporting and contradictory signals, and missing observations behind a particular alert. Return bounded structured data, not entire CSV histories.
3. **`replay_case(case_id: str)`** — replay one **pre-registered**, clearly `REAL_REPLAY` or `SYNTHETIC_INJECTION` scenario and return metrics + output. This is a read-only demonstration/test action. It must not mutate the model, train on test cases or touch actual facility controls.

Implement `assess_station` first. If time becomes critical, two tools — assessment and evidence — are enough; the UI can invoke a local fixture runner directly. Do not expose arbitrary SQL, file paths, shell commands, URL fetching, model retraining, SCADA operations or unrestricted data exports to the agent.

### Structured output contract

All model output is typed JSON / Pydantic and independently validated. A compact response may look like:

```json
{
  "station_id": "43014",
  "as_of_utc": "2023-04-01T00:00:00Z",
  "origin": "SYNTHETIC_INJECTION",
  "status": "INVESTIGATE",
  "severity": "watch",
  "data_quality": "SUFFICIENT",
  "model_version": "pump-baseline-v1",
  "policy_version": "attention-v1",
  "source_hash": "sha256:example-not-a-real-hash",
  "findings": [
    {
      "pump_id": "P2",
      "metric": "median_cycle_seconds",
      "observed": 151.0,
      "expected": 103.0,
      "units": "s",
      "persistence_windows": 5,
      "possible_causes": ["restriction", "changed inflow", "reduced pumping performance"],
      "alert_id": "demo-case-P2"
    }
  ],
  "missing_evidence": ["cycle-resolved wet-well drawdown"],
  "recommended_action": "Request operator inspection; verify conditions before dispatch"
}
```

**Illustrative schema only.** These measurements, timestamps, and hash are fabricated examples and MUST NOT be shown as measured model results. Use `status` values `NORMAL`, `WATCH`, `INVESTIGATE`, `INSUFFICIENT_EVIDENCE`, `SOURCE_OFFLINE` with a documented, non-overlapping meaning. Distinguish **model anomaly score**, **operational alert priority**, and **data/evidence confidence**; never imply an uncalibrated score is an actual failure probability. Return structured validation errors instead of hallucinating missing stations or datasets.

### Agent contract: what it may and may not do

- **May:** ask which station/time to assess; call the assessment tool; fetch evidence; compare cases; communicate *what changed, what supports it, what contradicts it, and what to inspect*. Draft human-reviewed work orders with explicit source links and caveats.
- **Must not:** infer new sensor values, modify status/severity, conceal quality flags, claim a confirmed root cause, decide emergency control actions, operate pumps, bypass safety alarms, fabricate citations, or issue work orders automatically.
- **Must behave deterministically where it matters:** code determines alerts; agent prose is optional and may vary. If the agent is unavailable, the dashboard still renders the exact validated assessment with a template-based explanation.
- **Privacy:** send the agent only bounded, relevant assessment/evidence payloads. Use a locally hosted LLM where data restrictions require it, but do not require a local language model for a working demo. Keep utility raw telemetry within approved boundaries.
- **Safety:** whitelist stations, scenarios, and tools; validate all MCP inputs; apply least-privilege access; avoid arbitrary file/URL access; log each invocation, model version, replay case and returned evidence ID. Remote MCP requires appropriate authentication and transport security, and enterprise deployment requires security review. Do not give the agent a direct historian or PLC credential.

### SDK and integration choice

- Use the **official Python MCP SDK**. Its current v2 documentation uses `from mcp.server import MCPServer` and `@mcp.tool()`; inspect the *installed* SDK version and pin it. Do **not** paste a v1 `FastMCP` import into a v2 environment without verifying compatibility. Official reference: https://py.sdk.modelcontextprotocol.io/ .
- For a local Claude Code demo, **stdio** is usually simplest. Streamable HTTP may be appropriate for a separately hosted agent or UI; use it only if the deployment needs it.
- A minimal MCP adapter should contain almost no business logic: validate arguments → call `assess_station` → return validated JSON. Have at least one actual agent/MCP-client tool-call test, not merely an MCP server that starts.
- If the UI's agent integration is delayed, run the same Python inference function behind a tiny JSON REST endpoint, with MCP wrapping it or importing it. **The MCP demonstration should show the agent calling the trained pipeline, but it need not be the only path to the UI.**

**Preferred simple stack:** Python/Pandas/scikit-learn; Pydantic; official MCP Python SDK; pytest/Ruff/GitHub Actions; React/Next.js only if already chosen. FastAPI is **optional** for a chart-driven UI, not required for MCP. A queue, distributed datastore, cloud ML platform, Kubernetes, multi-agent team, and vector search are inappropriate for this demo unless essential requirements emerge.

**Read-only boundaries:** never connect to live PLC/RTU, never expose a control command endpoint, never write a live SCADA tag, never auto-dispatch maintenance orders. A scenario invocation changes only the selected *local demo fixture*, never a real asset. Do not suppress independent critical SCADA alarms.

### Evidence provenance contract

Every surfaced alert should be traceable using: `alert_id`, `station_id`, `pump_id`, `origin: REAL_REPLAY|SYNTHETIC_INJECTION`, `as_of_utc`, `observed`, `expected`, `deviation`, `rain_context`, `quality_state`, `quality_flags`, `supporting_evidence`, `contradictory_evidence`, `unavailable_evidence`, `detector_trace`, `state_transition_reason`, `source_signal_ids`, `source_hash`, `model_version`, `policy_version`, `inspection_suggestion`. This can live in one core Pydantic model with small summary/evidence views. Preserve the original input and do not let the LLM generate these numeric fields.

**Example operator explanation (synthetic):**
> “Station 43014 / Pump 2 — INVESTIGATE (simulation). Median runtime exceeded its rain-conditioned expected range for five consecutive windows. Pump-state records are fresh; current rainfall does not explain the drift. The level sensor is too sparse to confirm individual-cycle hydraulic drawdown. Consider restriction, altered operating conditions or pumping-performance loss, then request an inspection. This is not a confirmed diagnosis.”

## 7. Operator interface: the judge should be able to interrogate us

**Screen 1: Control-room overview.** ISA-101-inspired restrained grey palette; no gratuitous red/green. Show station, pump, last data timestamp, data quality, alert state, and the few highest-value issues. A conspicuous `SIMULATED` / `REPLAY` label is required.

**Screen 2: The evidence drawer.** Click one alert and show:
1. Raw signal chart + signal IDs and UTC timestamps.
2. Quality filters applied and amount excluded.
3. Observed versus model-expected behavior, rain and duty context.
4. Change trajectory and why this time window crossed the escalation threshold.
5. Positive evidence, contradictory evidence, and missing evidence.
6. Model/data hash, policy version, replay/synthetic origin, recommended inspection.

**Screen 3: Reliability lab.** Choose S1–S6, compare A/B/C/D, change the seed only if the benchmark is reproducible, and inspect actual evaluation numbers. Include a one-click **break the sensor** action that results in safe abstention. An honesty panel says “What the model cannot know.”

**Minimal UI = good.** A single page with clickable station tiles, chart, selector, evidence drawer and evaluation strip is enough. Never show synthetic values as unqualified live city data.

## 8. Indiana story and five-minute demonstration

The relevant local examples are actual recorded overflow events, **not** the UK training data. Cite the official Bloomington SSO record in the demo. In particular, the April 11, 2024 Morningside Lift Station equipment-related record provides a local consequence. The public record does **not** establish that the event had observable gradual degradation or that Dragonfly could have prevented it. Fishers historical cases may be used only if primary reporting confirms date/cause; do not conflate 2026 flood reports with a 2026 mechanical lift-station breakdown. A wastewater treatment plant filter failure is not a lift-station pump fault.

**The story is: “Documented incident → missing hindsight data → scientifically testable what-if → trustworthy live system.”**

### Five-minute scripted arc

**0:00–0:30, reality:** “Indiana has documented sanitary sewer overflows. Here is the source record, date and reported impact. We don't have the pre-event station historian, so we won't pretend to have reconstructed its cause.”

**0:30–1:05, mentor question:** “Why not give everything to ChatGPT? You could, and it could train a predictor. But what would an operator trust the next morning when the sensor is stale and a storm arrives? The reliability pipeline is the actual product.”

**1:05–2:15, live test:** select healthy rainy period. Show simplistic alert burden and the contextual model's interpretation. Then select synthetic gradual deterioration hidden inside real Wessex replay. Compare A/B/C in identical conditions; show first detection and synthetic failure boundary. If the model misses it, acknowledge and explain.

**2:15–3:10, open the black box:** click alert → original pump transitions, valid cycles, rainfall, predicted/observed residual, evidence, exclusions, timestamped state transitions, version/hash. Explain why this incident deserves attention instead of 30 distracting alerts.

**3:10–3:45, attack reliability:** break level sensor / remove rainfall. Demonstrate `INSUFFICIENT_EVIDENCE` or appropriately downgraded evidence status, while preserving any genuine safety alarm. The system doesn't bluff.

**3:45–4:30, show engineering:** repo and commits, test/CI green, one command to reproduce the evaluation, real-vs-simulated provenance, AI corrections, data/privacy boundary.

**4:30–5:00, business + vision:** “We sit above existing SCADA and maintenance platforms. Wastewater is the proof-of-concept for context-aware, selectively attentive infrastructure intelligence. The next milestone is a pilot with labeled maintenance history and operator feedback, not a grand claim of prevented disasters today.”

**Optional 30–45s backup video:** assemble from **real recorded interface footage** with Remotion/FFmpeg and concise captions. Visualize conceptual dragonfly attention with clearly marked illustration; do not fake historical Indiana surveillance/utility footage. If time is constrained, make a screen recording, not AI cinema.

## 9. Engineering work split and schedule

Follow the repo `PLAN.md` ownership unless the team requests otherwise:

- **David (data/ML):** audit dataset, cycle pairing, rain joins, baseline/regression, residual detector, synthetic injections and evaluation script.
- **Praneetha (UX):** clear operator view, evidence drawer, reliability lab UI, high-performance HMI and accessible scenario flow.
- **Dhruv (backend/MLOps):** define typed model-output contract, implement minimal read-only MCP server, connect a single agent to real tool calls, reuse core inference through optional API/UI, CI, provenance logging, secrets hygiene and offline fallback. Build Ignition only if core done.

**Priority sequence (adapt to time remaining):**
1. **P0, usable foundation:** exact data slice, source hashes, lint/tests, API + visible UI.
2. **P0, reliability:** pump pairing, quality gate, rain-aligned features, Model 0, replay state.
3. **P0, one MCP vertical slice:** minimal read-only server exposes the exact assessed result; one agent makes a real tool call; if connection fails, use direct JSON view. Add Model 1 / advanced selector only if time allows.
4. **P0, proof:** evidence tool + evidence drawer and `reports/evaluation.json`, one-command test/replay, human-readable limitations, verify agent cannot change severity.
5. **P1:** S5/S6, draft work order, additional flow/pressure, quality metrics and model ablation.
6. **P2:** Ignition panel, polished backup video, multi-industry extensions, live connectors.

**Cut rule:** If time gets tight, drop Model 1 and use a robust rain-aware statistical baseline that genuinely works. **Do not drop provenance, test isolation, bad-data handling, or honest claims.** The most sophisticated model with untrusted data is worse than the simpler model with a reproducible reliability story.

### Repository layout suggestion (adapt to existing code, do not churn completed work)

```text
README.md
PLAN.md
CLAUDE.md                 # this master handoff
backend/
  app/                    # read-only data adapters, quality, model, attention, evidence, core inference
  tests/                  # fixture-backed QC, no-leakage, detection and API tests
  scripts/                # train, evaluate, export a small replay
  mcp_server.py           # thin typed MCP adapter, imports core inference
  agent.py                # single agent; only consumes MCP tool results
frontend/                 # existing UI stack, not necessarily new scaffold
fixtures/                 # tiny traceable public Wessex-derived and labeled synthetic inputs
reports/
  evaluation.json         # generated real results
  evaluation.md
  data_quality.json
  ai_corrections.md
  decisions.md
```

**Reproducibility target:** Document exact commands for `install → run tests → train/restore model → evaluate → start API/UI`. Provide a 2-minute offline fallback replay with a tiny self-contained fixture. No API key should be necessary for core inference/demo. CI should check unit tests, static checks and obvious secret leakage.

## 10. Acceptance criteria — do not call it done until these pass

- [ ] Real Wessex signal slice ingested; data source, time window, unit and hash visible.
- [ ] Per-pump event pairing correct, deduplicated, and tested against adversarial transitions.
- [ ] Rain joins and features are as-of correct; no future leakage; 2023 test not used for threshold tuning.
- [ ] At least one reliable pump-specific baseline producing observed vs expected with reproducible code.
- [ ] Dragonfly attention has *real effect* in a frozen ablation, not just a branded wrapper.
- [ ] Storm negative control, synthetic gradual fault, duty/standby control, and sensor-corruption test all execute through the same inference path.
- [ ] A full evidence packet is available for every surfaced warning, including missing/contradictory evidence.
- [ ] MCP tool `assess_station` returns a validated real model assessment (or explicit abstention) using exactly the same inference as the non-agent view.
- [ ] One actual agent/MCP client successfully calls the tool and quotes the returned evidence without manufacturing severity, missing readings, or root cause.
- [ ] Simulated failure, rain, and bad-sensor cases work if the agent is offline; no model training happens during tool invocation.
- [ ] Bad data visibly lowers confidence or triggers abstention. A real critical SCADA-style high-level alarm is never muted by rain suppression.
- [ ] Evaluation report records actual metrics, denominators, configuration, synthetic ground-truth isolation, and observed limitations.
- [ ] UI is genuinely interactive, no static mock alert pretending to be ML output; scenario replay is labeled.
- [ ] Core works fully without cloud LLM or live infrastructure systems.
- [ ] Repo shows CI/tests, source attribution and a truthful AI corrections/decisions log.
- [ ] An unfamiliar judge can understand the “why not ChatGPT?” distinction through one on-screen experiment in under 60 seconds.

## 11. Research and standards (guide design, don't pretend to be certified)

- Dragonfly selective attention: Wiederman & O'Carroll (2013), *Selective attention in an insect visual neuron*, https://pubmed.ncbi.nlm.nih.gov/23260469/ . Use as inspiration for selecting meaningful signals from clutter.
- Temporal target prediction: *A predictive focus of gain modulation encodes target trajectories in insect vision* (2017), https://doi.org/10.7554/eLife.26478 . Use as analogy for persistence/trajectory tracking, not evidence that the product is biologically identical.
- Wessex Water's supplier challenge and Q&A: evaluate against real operator demands including alerts, latency, quality, available sensor types and adaptation. Verify exact criteria at the source.
- NIST SP 800-82 Rev. 3, https://csrc.nist.gov/pubs/sp/800/82/r3/final ; read-only OT boundaries, least privilege, reliability engineering.
- ISA-101 human-machine interface guidance and ISA-18.2 alarm management principles; design influence only, **not compliance claims**.

## 12. Start executing (Claude Code task instruction)

**Begin immediately by producing a short repository status: what files exist, what data is accessible, what tests run, current risks, and the next 3 deliverables. Then implement the smallest vertical slice across ingestion, robust baseline, typed `assess_station` inference, MCP tool, one agent call, and live UI.** Do not respond only with another plan unless an essential resource is truly blocked.

After each slice: run tests; show concrete outputs; record remaining known failure modes; commit work with truthful messages. Build the reliability demonstration as a first-class feature. When asked “What exactly does Dragonfly improve over a one-off ChatGPT upload?”, **demonstrate with controlled data and an inspectable evidence trace before answering in marketing language.**
