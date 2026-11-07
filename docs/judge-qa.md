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
10. **Full end-to-end browser and accessibility tests in CI** (specified in §11.1, not built yet).

## Questions judges are likely to ask

- **"Why not a simple threshold rule?"** Same cases, untuned dev data (David's harness, `reports/evaluation.json`): Dragonfly caught 112 of 114 vs 111 of 114 for the simple rule, warned a median 8.4 days ahead vs 5.3, false-alarmed on 3 of 30 single bad days vs 30 of 30, and raised 0.49 real alerts per pump per 6 months vs 4.58. Same recall, three more days, about 10× fewer false alerts. Caveat: untuned dev numbers; final ones come from the frozen test run.
- **"Why not just give the data to ChatGPT?"** It could build a forecast. What an operator trusts the next morning is a pipeline that measures pump capacity directly, ignores rain by physics, checks its own data, says when it doesn't know, and is benchmarked on every change.
- **"Did you train a model?"** Each pump learns its own normal every day from its own history, and about 7 settings are tuned on 2022 data. We deliberately did not train a black box on failures: there are no failure labels, and a model trained on faults we planted would learn our planting method. We tested two learned alternatives; the simpler model held up.
- **"Would this have prevented the Morningside spill?"** We can't say that. No telemetry from that station exists. In our rebuild on a UK stand-in, if it was a gradual clog, Dragonfly warned about 2–3 days before the trip. If it was a sudden trip, we catch it at onset, the same as a working alarm.
- **"How accurate is it?"** On held-out planted faults, with intervals and denominators (MODEL_CARD rung 2). On real data: one real precursor caught 9 days early, and 7 of the 16 pump removals that showed a warning sign. 86% of removals in the data gave no warning sign at all.
- **"How did AI shape the build?"** Three people each drove a coding agent. Agents handed work to each other on a GitHub board and reviewed each other's PRs, and every PR was benchmarked. Real data corrected the plan several times: the sibling rule, the 5→10-minute silence rule, the run-time cap, the "8 of 9 pumps" count, and the weak-label finding.
- **"Can it run without the cloud?"** Yes. The detector and API are local. The language model is optional and swappable for a local one.
