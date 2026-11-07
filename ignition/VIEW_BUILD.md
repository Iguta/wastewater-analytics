# Building the Dragonfly Perspective view (on the demo laptop)

Design and rationale: [DESIGN.md](DESIGN.md). This file is the click-by-click build. Read-only throughout: memory tags only, no device or OPC writes.

**Status:** the tag file and the gateway script's logic are tested against the real API (`python3 ignition/tests/test_poll.py`, 11 tests). The script's logic was also run under Ignition 8.3.10's own Jython 2.7.4 (from the `inductiveautomation/ignition:8.3` image) against the live API and produced the same 106 tag values; that run found and fixed a non-ASCII-source error that Python 3 could not show. The tag import, the gateway timer and the Perspective view have **not** been run in a gateway. Steps 3 to 5 can only be done in the Designer, so treat their bindings as a first draft to check on the gateway.

## 0. Before you start

```bash
make setup
make serve
curl http://127.0.0.1:8000/api/health
```

The last command must print `"status":"ok"`.

## 1. Import the tags

Designer, Tag Browser, right-click the `[default]` provider, **Import Tags**, choose `ignition/tags/Dragonfly.json`. You get `[default]Dragonfly/` with 108 memory tags (`_meta`, one folder per station, `pumps/P1..P3`). Collision policy: Overwrite.

Then set two tags by hand:

| Tag | Value |
| --- | --- |
| `[default]Dragonfly/_meta/api_base` | `http://127.0.0.1:8000` for a native gateway, `http://host.docker.internal:8000` for the Docker image |
| `[default]Dragonfly/_meta/as_of_utc` | the replay clock, for example `2022-06-03T00:00:00Z` (a date from 2022-03-16 to 2023-12-31) |

## 2. Install the gateway script

1. Designer, **Project Browser, Scripting, Project Library**, new script `dragonfly_poll`. Paste all of `ignition/gateway/dragonfly_poll.py`.
2. **Gateway Events, Timer**, new timer: fixed delay, **60000 ms**, shared thread. Script: `dragonfly_poll.poll()`
3. Check in the Gateway status page, or the Designer script console, that `[default]Dragonfly/_meta/poll_ok` becomes `true` within a minute and `last_poll_utc` updates.

If `poll_ok` is `false`, `poll_error` says why (for example "Dragonfly API: ..."). The tiles then keep their last values and "Data up to" keeps its old time, so nothing looks fresh.

## 3. View: layout

New Perspective view `Dragonfly`, a **Flex container** (column, grey background `#D9DCDF`, text `#1B1F23`), three children:

1. **Header** (Flex row, background `#3B434B`, text white)
   - Label "Dragonfly AI", bold.
   - Label, tag binding to `[default]Dragonfly/_meta/origin_text` (the origin badge, always visible).
   - Label, tag binding to `[default]Dragonfly/_meta/data_up_to`.
2. **Banner**, a Label, red fill `#B42318`, white text, "Server not reachable". `meta.visible` expression binding: `!{[default]Dragonfly/_meta/poll_ok}`
3. **Body** (Flex row, wrap), two columns:
   - Left: three station tiles (step 4).
   - Right: the safety strip, then the attention queue (step 5).

## 4. Station tile (one embedded view `StationTile`, parameter `station`)

Use a **Flex Repeater** in the left column with three instances `[{"station":"44371"},{"station":"45385"},{"station":"45078"}]`, path to the view `StationTile`. Inside `StationTile` (panel `#F4F5F6`, border `#B8BEC4`), tag bindings use an **indirect tag** path: `[default]Dragonfly/{view.params.station}/<tag>`.

| Component | Binding |
| --- | --- |
| Label (title, bold) | `verdict` |
| Flex Repeater of pump chips | one instance per pump; the pumps of a station are `P1`, `P2` (and `P3` at 45078), so list them as the repeater's instances parameter `[{"pump":"P1"},{"pump":"P2"}]` (add `P3` for 45078 via an `if` expression on `{view.params.station}`) |
| Pump chip Label | text `pumps/{pump}/chip_text`; style class by `pumps/{pump}/status` (below) |
| Label `Evidence: ...` | `evidence_text` |
| Label | `level_sensor_line` |
| Label | `changes_line` |
| Label | `storm_line` |
| Label | text `Data up to ...`: use `as_of_utc` |

## 5. Safety strip and attention queue

**Safety strip** (panel with title "Safety (SCADA-equivalent checks)"):

- Flex Repeater, `instances` bound to tag `[default]Dragonfly/_safety_all_json` (a Document tag holding a list), each instance is a Label showing `{value.display_name}: {value.text}` (the `text` field already has the section 10.2 wording).
- Empty state Label, `meta.visible` bound to `{[default]Dragonfly/_meta/safety_count} = 0`, text exactly: `No safety findings. SCADA-equivalent checks; real setpoints unknown.`

**Attention queue** (panel with title "Attention queue"):

- Flex Repeater, `instances` bound to `[default]Dragonfly/_queue_all_json`, instance view `QueueRow` with parameters taken from each item: `rank`, `display_name`, `pump_id`, `status`, `status_text`, `change_pct`, `evidence`, `summary`, `opened_on`, `days_open`.
- `QueueRow` shows: rank (`1 of 3`), `display_name` + `pump_id`, `summary`, `Opened {opened_on}, flagged {days_open} days`, `change_pct` (format `0` plus `%`), `Evidence: {evidence}`, and a status Label with text `status_text` and the style class below.
- Empty state Label, `meta.visible` bound to `{[default]Dragonfly/_meta/queue_count} = 0`, text bound to `[default]Dragonfly/_meta/empty_queue_text`. It never says "All clear".
- Show the whole list in the repeater; the React UI cuts at 5 and collapses the rest, and for this view showing every row is acceptable.

## 6. Status style classes (section 10.2)

Create three style classes in the Perspective theme and apply them with this expression on `props.style.classes` (replace the tag path with the status value; for a queue row use `{view.params.status}`):

```
if({value} = 'INVESTIGATE', 'dragonfly/investigate',
 if({value} = 'WATCH', 'dragonfly/watch',
 if({value} = 'INSUFFICIENT_EVIDENCE' || {value} = 'SOURCE_OFFLINE', 'dragonfly/hatch', 'dragonfly/normal')))
```

| Class | Background | Text | Border |
| --- | --- | --- | --- |
| `dragonfly/investigate` | `#B42318` | `#FFFFFF` | `#B42318` |
| `dragonfly/watch` | `#FFC53D` | `#3A2800` | `#FFC53D` |
| `dragonfly/normal` | `#F4F5F6` | `#1B1F23` | `#B8BEC4` |
| `dragonfly/hatch` | `#F4F5F6` (solid chip; text never sits on a hatch) | `#1B1F23` | dashed `#B8BEC4` |

Colour is never the only cue: the label text always names the status, and the status Labels carry the shape (`◆` Investigate, `▲` Watch, `–` Normal) as a prefix in the text expression. No green anywhere.

## 7. Check it against the React UI

With the same `as_of_utc` in both, the verdicts, queue order, level-sensor lines and "Data up to" must match the React Stations tab. The test script prints the values the tags should hold for a given day, which is the quickest comparison:

```bash
python3 ignition/tests/test_poll.py
```

Then export the project to `ignition/project/` (Designer: File, Export) and commit it.

## Known limits of this mock

- Instance parameters for the pump chips and the safety and queue repeaters are the part most likely to need adjusting in Designer; the tag names and JSON fields they bind to are tested.
- The Perspective view file itself is not committed because it cannot be generated or validated outside Designer.
- No acknowledge, reset or override control exists anywhere (section 1).
