# data-testid list

Stub written 2026-11-07 by Praneetha's Claude Code, from ARCHITECTURE.md sections 10 and 11.1. Owner: Praneetha (`stream:ui`). Dhruv's `e2e/` tests may use only the ids below. To add or rename one, open a PR here and tag `@dhruvbangera`.

Naming: `kebab-case`. A repeated element gets an id plus a data attribute for its key (for example `data-station-id`, `data-pump-id`, `data-alert-id`, `data-status`).

## Frame (section 10.1)

| id | Element |
| --- | --- |
| `origin-badge` | Always-visible data origin badge (REPLAY or SIMULATION) |
| `as-of-label` | "Data up to {as_of} UTC" |
| `scrubber-prev` / `scrubber-next` | The `◀ day` and `day ▶` buttons |
| `scrubber-date` | Date picker input |
| `scrubber-live-date` | The `aria-live` region that announces the date |
| `replay-toggle` | Replay 1 day/s |
| `scrubber-end-note` | "End of data" note when Replay reaches the last day |
| `scrubber-range-error` | "Pick a date between {min} and {max}" |
| `scrubber-outage-marker` | Real-gap mark on the scrubber track (one per outage window) |
| `skip-to-investigate` | "Skip to first Investigate" (scenarios only) |
| `tab-stations` / `tab-incidents` / `tab-lab` | The three tabs |
| `server-banner` | Persistent "Server not reachable" banner |
| `state-loading` / `state-error` / `state-empty` | Per-screen states; `state-error` has a child `retry-button` |

`scrubber-prev`, `scrubber-next` and `replay-toggle` use the `disabled` attribute at the range edges (and `replay-toggle` at the last day).

## Stations tab (section 10.3)

| id | Element |
| --- | --- |
| `station-tile` | One per station (`data-station-id`) |
| `station-verdict` | One-line verdict in the tile |
| `pump-chip` | Pump status chip (`data-pump-id`, `data-status`) |
| `level-sensor-line` | "Level sensor: OK / Faulty since / No data" |
| `changes-since-yesterday` | Status changes line |
| `storm-line` | Storm outlook line |
| `safety-strip` | Safety strip; child `safety-empty` for the empty state |
| `high-level-unknown` | "High-level check: unknown (level sensor faulty)" entry in the safety strip |
| `attention-queue` | Queue container; child `queue-empty` for the empty state |
| `queue-row` | One row (`data-alert-id`, `data-status`); accessible name includes the status |
| `queue-tag` | "New today" / "Was Watch yesterday" |
| `queue-moved-up` | "Moved up: storm ahead" |
| `low-priority-toggle` | "Low priority (n)" |

## Evidence drawer (section 10.4)

| id | Element |
| --- | --- |
| `drawer` | The drawer; closes with Esc |
| `drawer-status-line` | Status line |
| `drawer-rain-line` | Rain line |
| `drawer-explanation` | Template explanation |
| `drawer-checklist` | Inspection checklist |
| `drawer-storm-prep` | "Storm prep" list (only when storm ahead) |
| `chart-capacity` | Pumping capacity chart; `chart-capacity-table` for the "View as table" view |
| `chart-runtime` | Observed vs expected run time chart; `chart-runtime-table` |
| `chart-table-toggle` | "View as table" toggle (any chart) |
| `drawer-raw-events` | Raw on/off timeline and level trace |
| `drawer-quality` | Cycles used and excluded |
| `drawer-evidence` | Supporting / contradictory / unavailable |
| `provenance` | Alert id, signal ids, source hash, model version, code version, origin |
| `provenance-model-version` / `provenance-source-hash` | Individual values |
| `work-order` | Draft work order; child `copy-work-order` button |
| `ask-input` / `ask-submit` | Ask Dragonfly |
| `ask-answer` | Answer or template fallback |
| `ask-offline` | "AI explanation unavailable (no API key)" |
| `ask-withheld` | "AI answer withheld" notice |
| `ask-grounding-badge` | "Checked against evidence" |

## Incidents tab (section 10.5)

| id | Element |
| --- | --- |
| `incident-card` | One per scenario (`data-scenario-id`) |
| `fact-chip` | VERIFIED / UNVERIFIED chip (`data-verified`) |
| `variant-card` | Variant A or B (`data-variant`) |
| `replay-variant-a` / `replay-variant-b` | Replay buttons. These are the A/B switch: there is no separate `replay-switch`. |
| `replay-banner` | "Variant X: assumed mechanism..." banner |
| `replay-output` | Container for the markers below, inside `replay-banner`. Shows "In this run it did not warn before the trip" when there was no Investigate before the failure. |
| `failure-marker` / `trip-marker` / `investigate-marker` | Replay markers |
| `outcome-row` | Result row per variant; gallons figures are inside `simulated-gal` |
| `simulated-gal` | Every gallons figure, always prefixed "Simulated:" |
| `reveal-truth` | "Reveal simulation ground truth" |

## Reliability Lab (section 10.6)

| id | Element |
| --- | --- |
| `lab-compare-table` | A / B / C table; values equal `/api/evaluation` |
| `lab-ablations` | Ablations table |
| `lab-heatmap` | Recall heatmap; `lab-heatmap-table` for the table view |
| `lab-no-report` | "Evaluation not run yet." |
| `exp-storm-test` / `exp-break-sensor` / `exp-cut-power` / `exp-one-bad-day` | Live experiment buttons |
| `lab-cannot-know` | "What the model cannot know" list |
| `lab-proxy-events` | "Real pump outages preceded by a warning: a of b" |

## Ignition (section 10.8)

Manual validation only. No test ids.
