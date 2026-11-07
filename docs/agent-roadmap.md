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

Everything below waits on the same gate: a utility's written authority, a data-sharing agreement, and the compliance work in `docs/compliance.md` (CMOM evidence, IEC 62443 zones, NIST AI RMF). Nothing trains on utility data before that.

1. **Real labels replace planted faults.** Maintenance records, work-order closures and the `/api/feedback` verdicts become ground truth (§6.8). Every labeled failure becomes a case in the per-PR benchmark (§11.6), so accuracy is finally measured on real failures, not injected ones.
2. **Shadow mode before alerts.** Run read-only beside the utility's SCADA for a season. Compare every Dragonfly finding with what crews found. Publish precision and lead time per station before anyone acts on an alert.
3. **Retune and revalidate on real data.** The same six hyperparameters, retuned on the utility's dev years and scored once on a held-out year, with the same gates. The learned baseline (§4.16) and the per-cycle model get a fair retry where labels exist.
4. **More signals, each earning its place.** Flow and pressure meters, motor current, VFD speed, and the utility's real alarm setpoints. Each one enters only if it beats the run/stop index on the benchmark.
5. **Fully local, no internet.** The detector, API, MCP server and UI already run on one machine. Add a local small language model for the explanation step, so the whole stack runs on-prem or air-gapped inside the utility's OT network zone.
6. **A fine-tuned small model for explanation only.** Trained on approved operator Q&A and the deterministic templates. It still only calls the three read-only tools and passes the grounding check; it never predicts, diagnoses or files anything.
7. **Deterministic action workflows.** Every finding type × status × evidence quality maps to one action: checklist, priority, response window and draft work order (extending `explain.py`). Each mapping is versioned and testable, never chosen by a model.
8. **CMMS and notification hand-off with human approval.** A supervisor approves the drafted work order and it is sent to the utility's CMMS or paging system. Nothing is dispatched automatically, and every hand-off is logged for the CMOM evidence trail.
9. **Consequence-weighted ranking.** GIS data (receiving waters, schools, basements downstream) and each station's overflow history weight the attention queue, alongside the forecast already used for storm readiness.
10. **Continuous monitoring of the model itself.** Drift checks on the capacity index and alert rates per station, a monthly reliability report, and a defined process to roll back to the last frozen version when a gate regresses.
