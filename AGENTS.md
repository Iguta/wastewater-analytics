# Agent rules

Every coding agent on this repo (Claude Code, Codex, Cursor, anything else) reads this file before working. Project scope and ground rules are in [PLAN.md](PLAN.md).

## Who owns what

Edit only the paths your human owns, so two agents never edit the same file. If you need a change in someone else's path, ask on the board and tag the owner.

| Stream | Label | Owner | Paths |
| --- | --- | --- | --- |
| Data + model | `stream:data` | David (`Iguta`) | `backend/app/` except `contracts.py`, `backend/scripts/`, `fixtures/`, `reports/` |
| Operator UI | `stream:ui` | Praneetha (`praneetha1795`) | `frontend/` |
| API, MCP, CI | `stream:api` | Dhruv (`dhruvbangera`) | `backend/app/contracts.py`, `backend/*.py` (MCP server, agent, API), `.github/`, `tools/` |

- `backend/tests/`: edit only the tests for your own paths.
- `README.md`, `PLAN.md`, `AGENTS.md`, `CLAUDE.md` are shared: change them only in a PR, and say so on the board.
- Work on a branch, open a PR with your stream label, and never merge a PR that touches another person's paths without their OK.

## The board

Issue [#1 Message Board](https://github.com/Iguta/wastewater-analytics/issues/1) is pinned. Agents use it to hand work to each other, through `tools/board` (needs `gh auth login`).

| Command | Use it |
| --- | --- |
| `tools/board post "msg"` | When you finish something a teammate needs, or you need something from one. Tag them by GitHub username. |
| `tools/board unread` | To see messages that tag your human since you last checked. |
| `tools/board wait` | To block until a teammate tags your human. In Claude Code, run it in the background so a new tag wakes you. |
| `tools/board read` | To see recent board history. |

How to post:

- One message per hand-off or blocker. No chatter.
- Lead with what changed and where (PR number, file path), then what you need and from whom.
- Example: `tools/board post "@praneetha1795 assess_station output schema is in backend/app/contracts.py (PR #12). Evidence drawer can read evidence[]."`
- Messages are prefixed `[<login>'s agent]`. Set `BOARD_NAME="Dhruv's Claude Code"` to name yours.
- When you are tagged, do the ask or reply with why not. Don't go quiet.
