# Ignition Perspective view: wireframe and tag layout

Design only. Owner: Praneetha (`stream:ui`). Spec: ARCHITECTURE.md section 10.8. **Building starts only after the 15:45 milestone, time-boxed to 45 min. If it does not show live tags by 16:20 it stays out of the demo.** The React UI is always the primary demo, and this view is the first thing cut (section 15).

## What it is

One read-only Perspective view in Ignition 8.3 with the station tiles, the safety strip and the attention queue, using the section 10.2 status presentation. It shows exactly what `GET /api/assess` returns, so there is one inference.

## Read-only rules

- The gateway script only **reads** from `http://127.0.0.1:8000/api/assess` and writes **memory tags** under `[default]Dragonfly/`.
- It never writes to a device, an OPC tag, or any tag that controls equipment. No button in the view writes anything.
- No acknowledge, reset or override controls (section 1, section 16).

## Data path

```text
Gateway timer script (every 60 s)
   -> system.net.httpGet("http://127.0.0.1:8000/api/assess?station_id=<id>&as_of_utc=<as_of>")  x 3 stations
   -> parse JSON -> write memory tags [default]Dragonfly/<station>/...
Perspective view -> bindings on those tags
```

Stations: `44371`, `45385`, `45078`. The replay clock is a memory tag the operator sets, `[default]Dragonfly/_meta/as_of_utc` (default `2022-06-03T00:00:00Z`), because the data is a replay, not live. The view always prints "Data up to {as_of} UTC", never "now".

## Tag layout

All tags are memory tags. Types in brackets.

```text
[default]Dragonfly/
  _meta/
    as_of_utc            [String]   replay clock, set by the operator, ISO 8601 with Z
    origin               [String]   REAL_REPLAY | SYNTHETIC_INJECTION | SIMULATED_INCIDENT
    model_version        [String]
    source_hash          [String]
    code_version         [String]
    last_poll_utc        [String]
    poll_ok              [Boolean]  false when any request failed
    poll_error           [String]   e.g. "HTTP 503"
  <station_id>/          (44371, 45385, 45078)
    display_name         [String]
    status               [String]   NORMAL | WATCH | INVESTIGATE | INSUFFICIENT_EVIDENCE | SOURCE_OFFLINE
    quality              [String]   SUFFICIENT | PARTIAL | INSUFFICIENT | SOURCE_OFFLINE
    as_of_utc            [String]
    level_sensor_line    [String]   "Level sensor: OK" | "Faulty since ..." | "No data" (derived by the script, same rule as the React UI)
    storm_line           [String]
    explanation          [String]
    safety_json          [Document] list of Finding (assess.safety)
    queue_json           [Document] list of Finding (assess.queue), already sorted by the API
    pumps/
      P1 ... P3
        status           [String]
        quality          [String]
        capacity_change_pct [Float4]
        ci_today         [Float4]
        ci_baseline      [Float4]
        valid_cycles     [Int4]
        runs             [Int4]
  _queue_all_json        [Document] all stations' queue findings merged and ordered (INVESTIGATE by capacity loss, then WATCH by days open)
  _safety_all_json       [Document] all stations' safety findings
```

The merged queue is built in the script with the same ordering as `frontend/src/derive.ts` (section 4.11), so both UIs rank the same way. The script needs no model code.

## Wireframe

Desktop screen, 1280 x 800. Grey background and panels, dark grey text, colour only for abnormal states, no green.

```text
+--------------------------------------------------------------------------------+
| Dragonfly AI | REPLAY - Wessex Water telemetry 2022-2023 (CC BY) - not live data   |
|                                          Data up to 2022-06-03 00:00 UTC       |
| [ Server not reachable ]   (only when poll_ok = false, red bar)                 |
+----------------------+---------------------------------------------------------+
| STATION TILES        |  SAFETY (SCADA-equivalent checks)                       |
| +------------------+ |  No safety findings. SCADA-equivalent checks; real      |
| | Wessex 44371     | |  setpoints unknown.                                     |
| | [P1 Investigate] | +---------------------------------------------------------+
| | [P2 Normal]      | |  ATTENTION QUEUE                                        |
| | Evidence: Suffic.| |  1 of 2  Wessex 44371 P1   -46%  Evidence: Sufficient   |
| | Level sensor: OK | |          Investigate: inspect this pump  [Was Watch]    |
| | Since 06-02: ... | |  2 of 2  Wessex 45078 P3   -46%  Evidence: Sufficient   |
| | Storm outlook:   | |          Watch: capacity is dropping                    |
| |  not available   | |  Low priority (n)  (collapsed)                          |
| +------------------+ |                                                         |
| (one tile per stn)   |                                                         |
+----------------------+---------------------------------------------------------+
```

Differences from the React UI, all deliberate to keep the build inside 45 minutes:

- **No evidence drawer, charts or Ask Dragonfly.** A queue row shows its summary; deeper evidence is in the React UI. A text line under the queue says so.
- **No scrubber.** The date is the `as_of_utc` tag; changing it is an operator edit in the tag browser, not a view control.
- **No Incidents or Lab tabs.**

## Perspective components

- **Frame:** Coordinate or Flex container, three rows: header, banner (visible only when `poll_ok` is false), body.
- **Origin badge and "Data up to" label:** Label components bound to `_meta/origin` and `_meta/as_of_utc` through expression bindings.
- **Station tiles:** Flex Repeater over the three station paths (instance parameter `station_id`), each tile bound to `[default]Dragonfly/{station_id}/...` through an indirect tag binding.
- **Pump chips:** nested Flex Repeater over `pumps/*`. Style class per status (below).
- **Safety strip and queue:** Flex Repeater bound to `_safety_all_json` and `_queue_all_json` (script transform parses the document into instances).
- **Queue rows** carry the status in their text (accessible name parity with the React UI).

## Status presentation (section 10.2, fixed)

| Status | Style class | Shape | Text |
| --- | --- | --- | --- |
| `NORMAL` | `st-normal` | grey dash | Normal |
| `WATCH` | `st-watch` | amber triangle | Watch: capacity is dropping |
| `INVESTIGATE` | `st-investigate` | red diamond | Investigate: inspect this pump |
| `INSUFFICIENT_EVIDENCE` | `st-hatch` | grey hatch on a solid chip | Not enough data (add "(warming up)" when the reason says so) |
| `SOURCE_OFFLINE` | `st-hatch` plus a red safety entry | grey hatch | Source offline: no data since {ts} |

Colours come from `frontend/src/styles/tokens.css`, copied into the Perspective theme as style classes (watch fill `#FFC53D` with `#3A2800` text; investigate fill `#B42318` with white text; grey `#4A5560`; page `#D9DCDF`; panel `#F4F5F6`). Shape and words always accompany colour. Text never sits directly on the hatch.

## Failure behaviour

| Situation | View shows |
| --- | --- |
| API unreachable or non-200 | Red "Server not reachable" bar; tiles keep the last values and the "Data up to" label keeps its old time, so nothing looks fresh |
| API returns an error body (`ToolError`) | `poll_error` is shown in the bar |
| No station data yet | "Loading..." text, never a blank view |
| Empty queue | "No pumps need attention as of {date}." (or the "Nothing flagged, but evidence is ..." line when quality is below Sufficient) |

## Build checklist (after 15:45)

1. Create the memory tag tree above (import a tag JSON).
2. Gateway timer script, 60 s, with the three `httpGet` calls, JSON parse and tag writes, wrapped in try/except so a failure sets `poll_ok = false` and never raises.
3. One Perspective view, "Dragonfly", per the wireframe, with the style classes.
4. Check against the live API at `127.0.0.1:8000`: tiles match the React UI for the same `as_of_utc`.
5. Export the project to `ignition/project/`.

Validation is manual only (section 10.8), and it sits outside `make verify`.

## Open questions for the owner of each decision

- **Dhruv:** is `GET /api/assess` reachable from the gateway on `127.0.0.1:8000` with no auth, as section 8.2 says? Does the gateway need a CORS or Host allowance? (None expected, because the call is server to server.)
- **David:** the gateway runs on his laptop (`localhost:8088`, native 8.3.10). Which is the primary and which is the Docker fallback on demo day?
