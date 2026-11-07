# Agent layer: today, next, and with real utility data

The detector decides. The agent only translates. Nothing below changes that rule.

## Today (built, on main)

| Piece | Where | What it does |
| --- | --- | --- |
| Predictive layer | `backend/app/` (detector, assess) | Computes every status, number and finding. Deterministic and versioned (`params.toml`). |
| MCP server | `backend/mcp_server.py` | Three read-only tools: `assess_station`, `get_evidence`, `replay_case`. No writes, no SQL, no shell. |
| Agent | `backend/agent.py`, `/api/ask` | Claude Sonnet 5.5 calls only those tools, then explains what they returned. It cannot compute. |
| Grounding check | `backend/app/grounding.py` | Every number and status word in the answer must match the tool output for the thing it names; forbidden phrases are blocked. On failure the answer is withheld and the template is shown. |
| Template explanation | `backend/app/explain.py` | The deterministic, always-on presentation layer. It is what operators see with no API key. |
| Operator feedback | `POST/GET /api/feedback` | "Was this right?" verdicts logged locally; never changes an assessment. |
| Any harness | §9 | Claude Code, Desktop, Cursor, VS Code and Codex connect to the same MCP server. |

**What the agent will not do:** estimate a missing reading, a failure probability or date, or a confirmed cause; suggest operating equipment; or run a what-if. Those are rules in the system prompt (§8.4), enforced by the grounding check.

## Next (scoped, not built)

0. **Harness: the Claude Agent SDK.** Replace the hand-written `tool_runner` loop in `agent.py` with the Agent SDK. The Dragonfly MCP server is declared as config; `allowed_tools` is exactly the three read-only tools, and every built-in tool (shell, files, web) is off. A post-turn hook runs the grounding check before anything reaches the operator. Sessions give conversation history (item 2). The model choice stays a single setting, so swapping Sonnet, Haiku or a local model behind a compatible endpoint is one line.
1. **Fixed output structure.** The agent returns a typed object (`summary`, `what_changed`, `supports`, `contradicts`, `missing`, `inspect`, `alert_ids`) instead of free markdown, so the UI renders the same layout every time. The grounding check runs per field.
2. **Conversation.** The drawer keeps a short history per alert, so an operator can ask follow-ups. Each turn still calls the tools; the history is never a source of numbers.
3. **What-if requests become a report request, not an answer.** "What happens if inflow doubles?" gets: "I can't run new analyses. I've logged this question for the reliability team." The question goes to the same local log as `/api/feedback`.
4. **A smaller model for translation.** Haiku 5.5 is enough for translation-only work. Measure it with `make agent-eval` (19/20 grounding gate) before switching.
5. **Rule changes go through the spec.** The system prompt is locked verbatim in ARCHITECTURE.md §8.4, so changes 1–3 are a `decision-change` PR plus new `agent_eval.toml` questions.

## With real utility data (needs a pilot and compliance clearance)

- **Real labels.** A pilot utility's maintenance records and operator verdicts become ground truth (§6.8), measured in the per-PR benchmark (§11.6).
- **Better predictive layer.** Tuned and validated on real failures, not only planted faults. The learned baseline (§4.16) is retried there.
- **A small local language model** for the translation step, fine-tuned on approved operator Q&A. It runs on-prem for utilities that cannot send data to a cloud model. It still only calls the MCP tools and never predicts.
- **The gate is compliance.** CMOM evidence, IEC 62443 zones and NIST AI RMF (`docs/compliance.md`) come before any real data or model training. Nothing trains on utility data without the utility's written authority.
