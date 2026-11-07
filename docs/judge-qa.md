# Judge Q&A

Short, honest answers for the five minutes at the table. Every number has a source in `docs/MODEL_CARD.md`, `docs/status.md` or `ARCHITECTURE.md`. If a number isn't there, don't say it.

## "What would you do with more time?"

1. **Real labels from a pilot.** Run in shadow mode beside a utility's SCADA for 90 days. Every operator "was this right?" click and every maintenance record becomes a labeled case in our benchmark. That turns "measured on planted faults" into "measured on real failures".
2. **A self-supervised model of each pump's cycles.** We have about 1.5M individual pump cycles. A small temporal network learns each pump's normal next cycle from its history, siblings and rain, with no failure labels needed. It enters through the same gates as a challenger. (Experiment in progress today; the result is reported either way.)
3. **A Bayesian model of each pump's true capacity, pooled across stations.** It gives an honest uncertainty band, and new stations borrow strength from the rest, so there's no warm-up period.
4. **Conformal calibration.** A guaranteed false-alarm rate per pump, without labels.
5. **A specialised local language model for the downstream agent.** Today, Claude Sonnet explains results behind a grounding check, and the model is swappable for a local one (Ollama on the team laptop). With pilot data: LoRA fine-tune a small (~3B) open model on real operator questions and real work orders, serve it on-prem behind the same grounding check, and score it with our 20-question agent eval. Fine-tuning teaches format and behavior. Facts stay in the tools, so the model never answers numbers from memory.
6. **Remaining-useful-life models** once failure dates exist (survival analysis).
7. **Read-only connectors** to the historians utilities run (OSIsoft PI, Ignition tag history, OPC UA).
8. **A second signal from the 1-minute level drawdown,** to corroborate pump capacity independently and to catch a failed check valve, which our index can hide.
9. **Expected run time per cycle** in the operator view (specified in §4.13, not computed yet).
10. **A CMMS and notification path** with human approval: draft work orders go to the utility's maintenance system only after a person signs off.
11. **A shadow-mode pilot where technician feedback (`/api/feedback`) becomes labels** in the benchmark.
12. **A field mobile workflow** for crews to see the evidence and record what they found.
13. **A wider tuning grid:** `W`, `G` and `min_effect` sit on the edge of the v2 grid.
14. **Full end-to-end browser and accessibility tests in CI** (specified in §11.1, not built yet).

## Headline (A§6.7)

Test tier, scored 1 time: on 125 held-out synthetic capacity-loss injections into real 2023 Wessex telemetry (≥20% loss over ≥7 days), Dragonfly raised INVESTIGATE before the pump trip in 125/125 (Wilson 95% 97.0–100%; 125 cases from 3 stations, 1 year), a median 4.8 days ahead. The test tier was scored 1 time. On the real 2023 replay, INVESTIGATE opens per pump per 180 days were 0.00 / 0.16 / 0.74. G5 fails (station shift 10/30) and is published as failing.

## Questions judges are likely to ask

- **"Why does a regulator care?"** In Fishers in 2012, IDEM fined the operator $5,250. Per IBJ (2013-08-09), the station listed no 24-hour emergency line and the overflow was not reported within 2 hours. Residents found it first. Both failures are about knowing in time. In our Fishers rebuild, Dragonfly flags the silent station in about 9 minutes. Its alert log is designed to support CMOM documentation (`docs/compliance.md`). We never say it satisfies a consent decree.
- **"Why not a simple threshold rule?"** Same dev cases (`reports/evaluation.json`, v2): Dragonfly caught 112 of 114 vs 111 of 114 for the simple rule, warned a median 6.3 days ahead vs 5.3, false-alarmed on 0 of 30 single bad days vs 30 of 30, and raised 0.25 real alerts per pump per 6 months vs 4.96. Caveat: dev numbers; v2 cut false alarms (duty swap 10 to 1, station shift 19 to 3 of 30) at the cost of about a day of warning.
- **"Why not just give the data to ChatGPT?"** It could build a forecast. What an operator trusts the next morning is a pipeline that measures pump capacity directly, ignores rain by physics, checks its own data, says when it doesn't know, and is benchmarked on every change.
- **"Did you train a model?"** Each pump learns its own normal every day from its own history, and about 7 settings are tuned on 2022 data. We deliberately did not train a black box on failures: there are no failure labels, and a model trained on faults we planted would learn our planting method. We tested two learned alternatives; the simpler model held up.
- **"Would this have prevented the Morningside spill?"** We can't say that. No telemetry from that station exists. In our rebuild on a UK stand-in, if it was a gradual clog, the first INVESTIGATE came about 31 h before the simulated trip, and with a 24 h response simulated overflow falls from 14,532 to 0 gal. If it was a sudden trip, we catch it at onset, the same as a working alarm.
- **"How accurate is it?"** On held-out planted faults, with intervals and denominators (MODEL_CARD rung 2). On real data: one real precursor (INVESTIGATE opened on 2022-06-04, about a week before the pump was taken out of service on 06-11), and 7 of the 16 pump removals that showed a warning sign. 86% of removals in the data gave no warning sign at all.
- **"How did AI shape the build?"** Three people each drove a coding agent. Agents handed work to each other on a GitHub board and reviewed each other's PRs, and every PR was benchmarked. Real data corrected the plan several times: the sibling rule, the 5→10-minute silence rule, the run-time cap, the "8 of 9 pumps" count, and the weak-label finding.
- **"Can it run without the cloud?"** Yes. The detector and API are local. The language model is optional and swappable for a local one.
- **"Why would a utility buy this instead of building it?"** The hard part is the evidence trail, not the detector. Utilities under an SSO consent decree or a CMOM program must show proactive maintenance; every Dragonfly alert carries a timestamp, signal ids, source hash, model and code version and a draft work order a human approves (A§7, A§10.4). It is read-only with no control write path, which fits IEC 62443 and NIST 800-82 thinking. The model card, grounding check and 19/20 agent-eval gate are the artifacts an AI RMF review asks for. Designed to support these, not certified: see `docs/compliance.md`.
