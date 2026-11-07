# Wastewater Analytics: Lift Station Early Warning

Early warning for wastewater lift station failures. It reads a utility's existing SCADA data **read-only**, spots pumps that are wearing out days before they fail, accounts for rain so storms don't trigger false alarms, and explains each alert in plain language.

Built at **Indy Init 2026** (Launch Fishers, November 7, 2026). Target category: **Community Impact**.

## The problem

Cities rely on **lift stations**, small pump stations that push sewage toward the treatment plant. When a pump fails and nobody notices in time, sewage overflows into yards, streets and creeks, bringing cleanup costs, state fines and lost public trust.

Most utilities already monitor these stations with SCADA, which logs wet well levels and pump on/off times. But SCADA is reactive: it alarms only once a level is critical or a pump has stopped. The early warning signs (pumps running longer, the well emptying more slowly, one pump doing more than its share) sit unused in data the utility already has.

Rain makes this hard. Storms also make pumps run longer, so simple thresholds either miss real problems or go off every time it rains, and operators learn to ignore them.

> Utilities already collect the data that predicts pump failures; we turn it into early, trustworthy warnings without new sensors or access to their control systems.

## Why it matters for Hoosiers

- **Fishers:** the sewer system the city now owns had repeated pump, power and controller failures from 2009 to 2012, with overflows toward Geist Reservoir and a state fine from IDEM.
- **Bloomington:** in 30 years of public overflow records (1,101 events), about **83%** were weather-driven and about **7%** came from equipment or power failures, the preventable kind. Overflow risk rises from about 1% on dry days to about 28% on days with 1 to 2 inches of rain.

## What it does

1. **Detects pump degradation** from data most utilities already log: run time per cycle, starts per hour, fill rate and duty share.
2. **Separates pump problems from storm inflow** by comparing each pump with its own expected behavior given the rain.
3. **Explains each warning** in plain language and drafts the work order.

## Who it's for

| User | Needs |
| --- | --- |
| Operator / technician | A quick, clear alert in the field: which pump, how urgent, what to check. |
| Maintenance planner | A station overview to prioritize and schedule work, especially before storms. |

## Architecture (planned)

```
Telemetry (simulated SCADA historian + real Wessex Water data)
        │  read-only ingestion
        ▼
Tag mapping layer  ──►  Data quality checks
        ▼
Feature engine (run time, starts, fill rate, duty share, rain)
        ▼
Risk model (expected run time vs actual, drift over days)
        ▼
LLM layer (plain-language explanation, draft work order)
        ▼
Dashboard (operator alerts, planner station overview)
```

## Data

- **Wessex Water**, "Rising mains telemetry, asset and rainfall data": real pump run-stop, wet well level, flow, pressure and hourly rainfall for 24 sewage pumping stations, 2022 to 2023. Licensed **CC BY**; contains data provided by Wessex Water.
- **City of Bloomington Utilities**, "Sanitary Sewer Overflows" (public domain, PDDL): used for problem evidence, not model training.
- **Open-Meteo** historical weather archive: daily rainfall for Bloomington.
- Simulated Fishers-style lift stations, with fictional names and approximate locations.

## Dataset and exploration notebooks

The raw data and our pre-hackathon exploration live in Google Drive, not in this repo, because the full telemetry files are too large for git (158 MB and 91 MB). Only small, trimmed per-station files will be committed here.

| Resource | What it contains |
| --- | --- |
| [Dataset folder (Google Drive)](https://drive.google.com/drive/folders/1x6gIb-EptRJB1q5HUdvWV4wzom5nesct?usp=sharing) | `wessex/` with the Wessex Water telemetry, key and rainfall files; `Sanitary_Sewer_Overflows_20261102.csv` (Bloomington) |
| [Wessex telemetry exploration (Colab)](https://colab.research.google.com/drive/1jbtOWFJ2bj38W74FqdsBRbqEo_zdHmNr?usp=sharing) | Signal lookup, station inventory and selection, pairing pump starts and stops into runs, one-day wet well sawtooth, baseline run times |
| [Bloomington overflow analysis (Colab)](https://colab.research.google.com/drive/1RPnH1W6hpVb9hyLlsvKKX60hOnVOUIGL?usp=sharing) | Data cleaning, overflow causes by category, rainfall reliability, overflow risk by daily rainfall |

These notebooks are exploration done before the event (planning and data study, which the rules allow). All application code in this repo is written during the hackathon.

## How to run

_Coming soon._

## How we built it

_Updated through the day: stack, how AI shaped the build, and where it needed correcting. See [PLAN.md](PLAN.md)._

## Team

- David Iguta Ndung'u: data, model, pipeline
- Sai Praneetha Chimalamarri: UI/UX
