# Dragonfly AI: Lift Station Early Warning

A read-only layer on top of SCADA that measures each sewage pump's real pumping capacity from the on/off timestamps utilities already log, and warns when one pump's capacity falls and stays down, before it fails.

Built at **Indy Init 2026** (Launch Fishers, November 7, 2026). Category: **Community Impact**.

**Demo video (2 min):** [final.mp4](https://github.com/Iguta/wastewater-analytics/releases/download/demo-video-draft/final.mp4)

## The problem

Cities rely on **lift stations**, small pump stations that push sewage toward the treatment plant. When a pump fails and nobody notices in time, sewage overflows into yards, streets and creeks, bringing cleanup costs, state fines and lost public trust.

SCADA alarms only once a level is critical or a pump has stopped. The warning signs that come before a failure sit unused in data the utility already has. Rain makes them hard to read: storms also make pumps run longer, so simple thresholds either miss real wear or go off every time it rains.

## Why it matters for Hoosiers

- **Bloomington, April 2024:** the Morningside lift station spilled 14,310 gallons during a storm after an equipment failure.
- **Fishers, 2009:** a power failure took down a lift-station controller whose backup battery was dead. No alarm went out, and 25,000 gallons spilled toward Geist Reservoir. The same manhole overflowed again in 2012, and IDEM fined the utility $5,250.
- **Bloomington, 30 years of public overflow records (1,101 events):** about 83% were weather-driven and about 7% came from equipment or power failures.

## What it does

1. **Measures pump capacity from on/off times alone.** The capacity index, `3600/run + 3600/fill`, cancels inflow, so rain barely moves it.
2. **Compares each pump with its own history,** with the sibling pump as a control group, so a station-wide change isn't blamed on one pump.
3. **Warns only when capacity falls and stays down:** Watch, then Investigate.
4. **Shows the evidence:** raw pump events, charts, data quality, and provenance down to the source file hash.
5. **Explains and drafts:** a plain-language explanation, an inspection checklist, and a draft work order for a person to review and file.
6. **Keeps safety checks visible:** source offline, high level and sensor faults, never suppressed. When evidence is thin, it says "not enough data".

Read-only by design: it never writes to a PLC or SCADA tag.

## Results

| What | Result |
| --- | --- |
| Rain test (real Wessex data) | Raw run time shifts 1.09–1.33× between wet and dry days; the capacity index stays within 0.96–1.03× on 8 of 9 pumps |
| Held-out 2023 test, planted capacity losses (≥20% over ≥7 days) | Investigate before the pump trip in **125 of 125** cases (95% interval 97–100%), median **4.8 days** ahead. Test tier scored once. |
| False alarms, held-out 2023 | Storm 0/30, duty swap 0/30, one bad day 0/30. **Station-wide shift 10/30: the one gate we still fail, published as is.** |
| Real pump, Wessex 44371 P1 (2022, development data) | Capacity down 46% on June 1; Investigate on June 3, about a week before the pump was taken out of service |
| Morningside simulation (assumed gradual clog, confidence 40%) | Investigate about 31 h before the simulated trip. With a 24 h repair, simulated overflow falls from 14,532 to 0 gal. |
| Fishers simulation (power loss) | Source offline flagged 9 minutes after the station went silent |

The Indiana cases are labeled what-if simulations built from public records, not reconstructions. No pre-failure telemetry exists for either station. Full method and limits: [docs/MODEL_CARD.md](docs/MODEL_CARD.md).

## Architecture

```text
Wessex Water telemetry (real, read-only) + scenario transforms
        ▼
Quality checks → daily capacity index → detector (baseline, sibling control, CUSUM, persistence)
        ▼
assess (one implementation) → typed contracts
        ├─► REST API ──► React operator UI · Ignition Perspective view (read-only)
        └─► MCP server ─► any AI agent (Claude Code, Desktop, Cursor, Codex)
                           └─ grounded explainer: every number must match the tool output
```

The detector and its rules decide everything. The AI only explains, and work orders are deterministic drafts. Spec: [ARCHITECTURE.md](ARCHITECTURE.md). Future scope: [docs/agent-roadmap.md](docs/agent-roadmap.md).

## How it's validated

- `make verify` runs on every change: lint, unit and contract tests, no-lookahead and determinism tests, the eval smoke gates, the UI build, an MCP smoke test, and 24 Playwright plus axe accessibility tests.
- A per-PR benchmark compares each change against main on the same development cases.
- Tuning used 2022 only. 2023 was scored once, and the result is in an append-only log.

## Data

- **Wessex Water**, "Rising mains telemetry, asset and rainfall data": real pump run/stop events, wet-well level and hourly rainfall, 2022 to 2023 (CC BY; contains data provided by Wessex Water). Stations used: 44371, 45385, 45078.
- **City of Bloomington Utilities**, "Sanitary Sewer Overflows" (public domain, PDDL): the Morningside scenario and overflow evidence.
- **Open-Meteo**: Indiana rainfall and the archived forecasts used for storm readiness.
- Public news and IDEM records: the Fishers scenario facts.

## Dataset and exploration notebooks

The raw data and our pre-hackathon exploration live in Google Drive, not in this repo, because the full telemetry files are too large for git (158 MB and 91 MB). Only small, trimmed per-station files will be committed here.

| Resource | What it contains |
| --- | --- |
| [Dataset folder (Google Drive)](https://drive.google.com/drive/folders/1x6gIb-EptRJB1q5HUdvWV4wzom5nesct?usp=sharing) | `wessex/` with the Wessex Water telemetry, key and rainfall files; `Sanitary_Sewer_Overflows_20261102.csv` (Bloomington) |
| [Wessex telemetry exploration (Colab)](https://colab.research.google.com/drive/1jbtOWFJ2bj38W74FqdsBRbqEo_zdHmNr?usp=sharing) | Signal lookup, station inventory and selection, pairing pump starts and stops into runs, one-day wet well sawtooth, baseline run times |
| [Bloomington overflow analysis (Colab)](https://colab.research.google.com/drive/1RPnH1W6hpVb9hyLlsvKKX60hOnVOUIGL?usp=sharing) | Data cleaning, overflow causes by category, rainfall reliability, overflow risk by daily rainfall |

These notebooks are exploration done before the event (planning and data study, which the rules allow). All application code in this repo is written during the hackathon.

## How to run

Prerequisites: [uv](https://docs.astral.sh/uv/), Python 3.12, Node 22, and `cloudflared` (optional, only for the remote tunnel).

```bash
make setup      # cd backend && uv sync --frozen; cd frontend && npm ci
make build-ui   # build the UI so the server can serve it
make serve      # http://127.0.0.1:8000 (API, plus the built UI at /)
```

| Command | What it does |
| --- | --- |
| `make verify` | The one check (`tools/verify`, also run in CI). Steps: lint and pytest, `eval-smoke`, UI build, `mcp-smoke`, Playwright e2e and axe. A step whose input files are missing prints `SKIP`. |
| `make eval-dev` | Evaluate the current params on the dev tier. |
| `make mcp` / `make mcp-http` | MCP server over stdio / Streamable HTTP. |
| `make agent-eval` | Grounding eval of the agent. Needs `ANTHROPIC_API_KEY`, otherwise it prints SKIP. |

Without `ANTHROPIC_API_KEY`, Ask Dragonfly shows the standard explanation.

## Use it from your agent

The MCP server is read-only and exposes three tools: `assess_station`, `get_evidence` and `replay_case`. Everything below runs from a clone of the repo after `make setup`. Replace `<repo>` with the absolute path.

| Harness | Configuration |
| --- | --- |
| Claude Code | `claude mcp add dragonfly -- uv run --project <repo>/backend python -m backend.mcp_server` |
| Claude Desktop | `{"mcpServers": {"dragonfly": {"command": "uv", "args": ["run", "--project", "<repo>/backend", "python", "-m", "backend.mcp_server"]}}}` |
| Cursor (`.cursor/mcp.json`) | The same `mcpServers` block |
| VS Code (`.vscode/mcp.json`) | `{"servers": {"dragonfly": {"type": "stdio", "command": "uv", "args": ["run", "--project", "<repo>/backend", "python", "-m", "backend.mcp_server"]}}}` |
| Codex (`~/.codex/config.toml`) | `[mcp_servers.dragonfly]` with `command = "uv"` and `args = ["run", "--project", "<repo>/backend", "python", "-m", "backend.mcp_server"]` |
| Remote (claude.ai custom connector, ChatGPT developer-mode connector) | `make mcp-http` plus `make tunnel` gives `https://<random>.trycloudflare.com/mcp`. |

Restart your agent after adding the server so it loads the tools.

**About the tunnel:** it exposes port 8001 only (never 8000 or `/api/ask`) and is up only during judging. It needs no auth because it serves only public CC BY data and labeled simulations. Real utility deployments would need OAuth and an on-prem host.

Example questions:

- "Which stations need attention as of 2023-03-01?"
- "Why is 44371 pump 1 flagged on 2022-06-05? Show the evidence."
- "Replay the Morningside scenario and tell me how early it warned."

## How we built it

Three people, each driving a coding agent, in one day.
- **Ownership:** each person owns their own folders.
- **Hand-offs:** the agents pass work to each other on a pinned GitHub issue board.
- **Review:** every PR is reviewed by a separate agent told to find reasons to reject it, and must pass `make verify` before merging.
- **Protected files:** the locked spec, gates, parameters and scenarios are protected by CODEOWNERS, so nobody, human or agent, can change them quietly.

Real data forced several corrections to the plan:
- a sibling-pump rule that subtracts only a shared drop;
- a 10-minute silence rule, after 5 minutes flickered;
- a cap on simulated run times;
- the finding that 86% of real pump removals gave no warning sign in the data.

## Team

- David Iguta Ndung'u: data, detector, fault injection, simulations, evaluation, Ignition view
- Sai Praneetha Chimalamarri: operator UI and UX, Ignition design
- Dhruv Bangera: contracts, API, MCP server, grounded agent, CI and validation, agent board

### Hook your agent up to the board

Each person owns their own folders, and our coding agents hand work to each other on the pinned [Message Board](https://github.com/Iguta/wastewater-analytics/issues/1) issue. Run `gh auth login` once, then read [AGENTS.md](AGENTS.md). Claude Code picks it up through `CLAUDE.md`, and a session-start hook shows any new tags.
