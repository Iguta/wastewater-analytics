# Wastewater Analytics: Lift Station Early Warning

Early warning for wastewater lift station failures. It reads a utility's existing SCADA data **read-only**, spots pumps that are wearing out days before they fail, accounts for rain so storms don't trigger false alarms, and explains each alert in plain language.

Built at **Indy Init 2026** (Launch Fishers, November 7, 2026). Target category: **Community Impact**.

## The problem

Cities rely on **lift stations**, small pump stations that push sewage toward the treatment plant. When a pump fails and nobody notices in time, sewage overflows into yards, streets and creeks, bringing cleanup costs, state fines and lost public trust.

Most utilities already monitor these stations with SCADA, which logs wet well levels and pump on/off times. But SCADA is reactive: it alarms only once a level is critical or a pump has stopped. The early warning signs (pumps running longer, the well emptying more slowly, one pump doing more than its share) sit unused in data the utility already has.

Rain makes this hard. Storms also make pumps run longer, so simple thresholds either miss real problems or go off every time it rains, and operators learn to ignore them.

> Utilities already collect the data that predicts pump failures; we turn it into early, trustworthy warnings without new sensors or access to their control systems.

## Why it matters for Hoosiers

- **Fishers:** in the sewer system the city now owns (then run by Hamilton Southeastern Utilities), a 2009 power failure took down a lift-station controller whose backup battery was dead, spilling 25,000 gallons toward Geist Reservoir. The same manhole overflowed again in 2012, and IDEM fined the utility $5,250.
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

Model card and validation ladder: [docs/MODEL_CARD.md](docs/MODEL_CARD.md)

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

Prerequisites: [uv](https://docs.astral.sh/uv/), Python 3.12, Node 22, and `cloudflared` (optional, only for the remote tunnel).

```bash
make setup      # cd backend && uv sync --frozen; cd frontend && npm ci
make build-ui   # build the UI so the server can serve it
make serve      # http://127.0.0.1:8000 (API, plus the built UI at /)
```

| Command | What it does |
| --- | --- |
| `make verify` | The one check (`tools/verify`, also run in CI). Steps: lint and pytest, `eval-smoke`, UI build, `mcp-smoke`, Playwright e2e and axe (e2e prints `SKIP` until `e2e/` lands). A step whose input files are missing prints `SKIP`. |
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
| Remote (claude.ai custom connector, ChatGPT developer-mode connector) | `make mcp-http` plus `cloudflared tunnel --url http://127.0.0.1:8001` gives `https://<random>.trycloudflare.com/mcp`. |

Restart your agent after adding the server so it loads the tools.

**About the tunnel:** it exposes port 8001 only (never 8000 or `/api/ask`) and is up only during judging. It needs no auth because it serves only public CC BY data and labeled simulations. Real utility deployments would need OAuth and an on-prem host.

Example questions:

- "Which stations need attention as of 2023-03-01?"
- "Why is 44371 pump 1 flagged on 2022-06-05? Show the evidence."
- "Replay the Morningside scenario and tell me how early it warned."

## How we built it

_Updated through the day: stack, how AI shaped the build, and where it needed correcting. See [PLAN.md](PLAN.md)._

## Team

- David Iguta Ndung'u: data, features, risk model, LLM explanations
- Sai Praneetha Chimalamarri: UI/UX, operator and planner dashboard
- Dhruv Bangera: API, CI/CD, deployment, security, Ignition integration

### Hook your agent up to the board

Each person owns their own folders, and our coding agents hand work to each other on the pinned [Message Board](https://github.com/Iguta/wastewater-analytics/issues/1) issue. Run `gh auth login` once, then read [AGENTS.md](AGENTS.md). Claude Code picks it up through `CLAUDE.md`, and a session-start hook shows any new tags.
