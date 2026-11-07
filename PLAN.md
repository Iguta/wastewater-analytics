# Build Plan: Indy Init 2026

Build window: **9:00 AM to 5:00 PM**. Devpost submission closes at **5:00 PM sharp**. Judges visit our table from 5:00 PM, about 5 minutes each.

## Goal

A **live, working** lift station early warning tool, built for **Community Impact** and scored on **The Build**. Judges should be able to use it, see the repo, tests and pipeline, and hear how AI shaped the work.

**Scope rule:** a small thing that works beats a big thing that doesn't. Each milestone ends with something demoable.

## Roles

| Person | Owns |
| --- | --- |
| David | Data loading, features, risk model, API, LLM explanations, tests, CI |
| Praneetha | Operator and planner screens, design system, accessibility, demo story, architecture diagram |
| Shared | Decisions log, README, Devpost submission, demo rehearsal |

## Milestones

| Time | Milestone | Done when |
| --- | --- | --- |
| 9:50 to 11:00 | **Skeleton** | Repo structure, CI running lint and tests, a hello-world app deployed or running end to end |
| 11:00 to 12:30 | **Data and features** | Trimmed Wessex station data loads; run times, starts, fill rate and duty share computed per pump per day; unit tests pass |
| 12:30 | Lunch | |
| 1:00 to 2:30 | **Risk model** | Expected-run-time model per pump with rain; drift score flags an injected fault; false-alarm check on untouched data |
| 1:00 to 2:30 | **UI (in parallel)** | Operator alert view and planner station overview on mock data |
| 2:30 to 3:45 | **Connect and explain** | UI reads real model output; LLM turns each alert into a plain-language explanation and draft work order |
| 3:45 to 4:30 | **Harden** | Tests green, README updated, Devpost draft submitted, architecture diagram added |
| 4:30 to 5:00 | **Freeze** | No new features; final Devpost edits; rehearse the 5-minute demo |

## Model approach

1. **Unit:** one pump, one day. Question: is this pump behaving worse than expected given today's conditions?
2. **Features:** median run time per cycle, number of starts, very short (<10 s) and very long (>10 min) runs, fill rate between runs, duty share, rain today, last 3 days and peak hour, day of week, month.
3. **Expected behavior:** predict each pump's run time from context (rain, season, duty). Residual = actual minus expected. A residual that keeps growing over several days means degradation; one bad day is noise.
4. **Evaluation:** inject a gradual fault into a healthy pump (stretch run times over two weeks) and measure detection, days of warning and false alarms. Train on 2022 (dry year), test on 2023 (wet year).
5. **Lessons from exploration:** pair pump starts and stops within each pump, never across pumps; pump imbalance can be normal duty/standby, so compare each pump with its own history.

## Data

- Stations: **45497** (clean, two balanced pumps, 1-minute level), **45078** (three busy pumps), **43014** (duty/standby example).
- Bring only trimmed per-station CSVs into the repo. Never commit the full 158 MB / 91 MB source files.
- Credit Wessex Water (CC BY) in the README and the app.

## Ground rules

- **Read-only:** nothing in this project writes to a control system.
- **Commit often**, with small, clear messages, so the history shows the work.
- **No secrets in the repo:** API keys go in environment variables.
- **Log AI corrections:** every time AI-generated code was wrong and we fixed it, add a line to the decisions log below.

## Demo plan (5 minutes)

1. **Problem (1 min):** lift stations, overflows, Fishers and Bloomington evidence. "We built this for Community Impact."
2. **Live product (3 min):** a pump degrading over several days gets flagged while SCADA alone would stay quiet; open the alert, read the plain-language explanation and work order; show rain not triggering a false alarm.
3. **How we built it (1 min):** repo, tests, pipeline, where AI needed correcting, and what we'd build next.

## Decisions and AI corrections log

| Time | Decision or correction | Why |
| --- | --- | --- |
| Before the day | Categorizer bug: `return "other"` was inside the loop, so only the first rule ran | Caught by checking output counts; fixed and covered by assertions |
| Before the day | Pump runs must be paired within each pump | Pairing across rows matched one pump's start with another's stop |
| | | |
