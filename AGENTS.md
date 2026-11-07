# Agent rules

Every coding agent on this repo (Claude Code, Codex, Cursor, anything else) reads this file before working. Project scope and ground rules are in [PLAN.md](PLAN.md).

## Who owns what

Edit only the paths your human owns, so two agents never edit the same file. If you need a change in someone else's path, ask on the board and tag the owner.

| Stream | Label | Owner | Paths |
| --- | --- | --- | --- |
| Data + model | `stream:data` | David (`Iguta`) | `backend/app/` except `contracts.py`, `assess.py`, `explain.py` (new files there default to David); `backend/scripts/`, `fixtures/` except `fixtures/ui/`, `reports/` |
| Operator UI | `stream:ui` | Praneetha (`praneetha1795`) | `frontend/`, `ignition/`, `docs/testids.md` |
| API, MCP, CI | `stream:api` | Dhruv (`dhruvbangera`) | `backend/app/{contracts,assess,explain}.py`, `backend/*.py` (MCP server, agent, API, agent eval), `backend/tests/conftest.py`, `backend/pyproject.toml`, `backend/uv.lock`, `Makefile`, `e2e/`, `fixtures/ui/`, `.github/`, `tools/`, `docs/` (except `docs/testids.md`), `.gitignore`, `.python-version`, `.vscode/`, `.cursor/` |

- `backend/tests/`: edit only the tests for your own paths.
- `README.md`, `PLAN.md`, `AGENTS.md`, `CLAUDE.md`, `ARCHITECTURE.md` are shared: change them only in a PR, and say so on the board.
- [ARCHITECTURE.md](ARCHITECTURE.md) is the locked build spec. If a decision you need is not in it, ask on the board instead of improvising.
- Work on a branch, open a PR with your stream label, and never merge a PR that touches another person's paths without their OK.

## How to write code here

Every agent, every file, model code included. The goal is the smallest change that fully works, readable at a glance.

1. **Before writing:** list every place the change must reach (callers, tests, fixtures, config). That is the scope. Extra features are not.
2. **Pick the first option that fully works:** delete or skip it; reuse a helper already in the repo; use the standard library or pandas directly; otherwise the minimum code that works. Never add a dependency for a few lines.
3. **No abstraction nobody asked for:** no wrapper, base class, config option, plugin point or "for later" code. No one-caller helpers. Keep the layering ARCHITECTURE.md §8.1 gives.
4. **Model code is plain pandas on the daily table.** Medians, MADs and one CUSUM loop. If a step needs scikit-learn, stop and ask on the board.
5. **Every new branch, loop or parser gets one small test** in `backend/tests/`, written before the code when it is a bug fix. Never weaken a test to pass.
6. **A known shortcut gets a comment:** `# shortcut: <the limit>, <when to upgrade>`.
7. **Comment only the why** the code cannot show, in one line.
8. **Before a PR:** run `make verify`, then `/simplify` (Claude Code) or an equivalent pass that removes anything the diff does not need. Paste the last 10 lines of `make verify` in the PR body.
9. **Never cut:** validation at the trust boundary (API and MCP inputs), error handling that prevents data loss, the read-only rule, and provenance fields.

**Model experiments are announced, not just run.** Before any tuning run, parameter change, or model experiment (grid, new baseline, new feature, threshold sweep), post on the board starting with `EXPERIMENT:` stating the question, the data tier (dev only), and the decision rule that would adopt it. Post the result starting with `RESULT:` with the numbers, including when it lost, and add one row to `reports/decisions.md`. Nobody tunes on 2023 or on the weak labels.

Claude Code users: `ponytail` is the house style and runs automatically; `/ponytail-review` before every PR.

## The board

Issue [#1 Message Board](https://github.com/Iguta/wastewater-analytics/issues/1) is pinned. Agents use it to hand work to each other, through `tools/board` (needs `gh auth login`).

| Command | Use it |
| --- | --- |
| `tools/board post "msg"` | When you finish something a teammate needs, or you need something from one. Tag them by GitHub username. |
| `tools/board unread` | To see messages that tag your human since you last checked. |
| `tools/board wait` | To block until a teammate tags your human. In Claude Code, run it in the background so a new tag wakes you. |
| `tools/board read` | To see recent board history. |

Every session:

1. Read what you missed: the Claude Code session-start hook prints it. Other agents run `tools/board unread`.
2. Start `tools/board wait` in the background. When it wakes you, handle the tag, then start it again. If it exits with an error, start it again.
3. Before you start a piece of work, check that its paths are yours (table above).

How to post:

- One message per hand-off or blocker. No chatter.
- Lead with what changed and where (PR number, file path), then what you need and from whom.
- Example: `tools/board post "@praneetha1795 assess_station output schema is in backend/app/contracts.py (PR #12). Evidence drawer can read evidence[]."`
- Messages are prefixed `[<login>'s agent]`. Set `BOARD_NAME="Dhruv's Claude Code"` to name yours.
- When you are tagged, do the ask or reply with why not. Don't go quiet.
