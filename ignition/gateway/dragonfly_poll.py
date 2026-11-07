# Dragonfly gateway timer script (Ignition 8.x, Jython 2.7: no f-strings, no type hints).
# READ-ONLY: it only calls GET /api/assess and GET /api/timeline, and writes MEMORY tags under [default]Dragonfly/.
# It never writes to a device, an OPC tag or any tag that controls equipment (ARCHITECTURE sections 1 and 10.8).
#
# Everything above poll() is plain Python so ignition/tests/test_poll.py can run it outside Ignition.
# poll() is the only code that touches system.*.
import json

BASE = "[default]Dragonfly"
STATIONS = ["44371", "45385", "45078"]
DOC_TAGS = set(["safety_json", "queue_json", "_queue_all_json", "_safety_all_json"])

STATUS_WORD = {"NORMAL": "Normal", "WATCH": "Watch", "INVESTIGATE": "Investigate",
               "INSUFFICIENT_EVIDENCE": "Not enough data", "SOURCE_OFFLINE": "Source offline"}
STATUS_TEXT = {"NORMAL": "Normal", "WATCH": "Watch: capacity is dropping", "INVESTIGATE": "Investigate: inspect this pump",
               "INSUFFICIENT_EVIDENCE": "Not enough data", "SOURCE_OFFLINE": "Source offline"}
QUALITY_WORD = {"SUFFICIENT": "Sufficient", "PARTIAL": "Partial", "INSUFFICIENT": "Not enough", "SOURCE_OFFLINE": "Source offline"}
QUALITY_RANK = ["SUFFICIENT", "PARTIAL", "INSUFFICIENT", "SOURCE_OFFLINE"]
ORIGIN_TEXT = {
    "REAL_REPLAY": u"REPLAY · Wessex Water telemetry 2022–2023 (CC BY) · not live data",
    "SYNTHETIC_INJECTION": u"SIMULATION · synthetic fault in real telemetry · not real station data",
    "SIMULATED_INCIDENT": u"SIMULATION · scenario · not real station data",
}


def ts_text(iso):
    # "2022-06-01T00:00:00Z" -> "2022-06-01 00:00"
    return iso.replace("T", " ").replace(":00Z", "").replace("Z", "")


def prev_day(day):
    # day is "YYYY-MM-DD"; pure-Python so it works in Jython without datetime tricks
    import datetime
    d = datetime.date(int(day[0:4]), int(day[5:7]), int(day[8:10])) - datetime.timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def verdict(a):
    parts = ["%s %s" % (p["pump_id"], STATUS_WORD[p["status"]]) for p in a["pumps"]]
    return "%s: %s" % (a["display_name"], ", ".join(parts))


def level_sensor_line(a):
    for f in a["safety"]:
        if f["type"] == "SOURCE_SILENT":
            return "Level sensor: No data"
    for f in a["queue"]:
        if f["type"] == "SENSOR_FAULT":
            return "Level sensor: Faulty since %s UTC" % ts_text(f["since_utc"])
    return "Level sensor: OK"


def storm_line(a):
    s = a.get("storm")
    if not s:
        return "Storm outlook: not available (no station location in the public data)"
    if s["storm_ahead"]:
        return "Storm ahead: %s in forecast over 48 h, gusts to %s mph (archived forecast issued %s, replayed)" % (
            s["forecast_rain_48h_in"], s["max_gust_48h_mph"], s["issued_on"])
    return "No storm in the 48 h forecast (archived forecast issued %s, replayed)" % s["issued_on"]


def changes_line(a, timeline, prev):
    # timeline: list of TimelineDay for the day before as_of, or None when the request failed
    y = None
    for d in (timeline or []):
        if d["day"] == prev:
            y = d
    if y is None:
        return "Changes since yesterday: not available"
    was = {}
    for p in y["pumps"]:
        was[p["pump_id"]] = p["status"]
    diffs = []
    for p in a["pumps"]:
        w = was.get(p["pump_id"])
        if w and w != p["status"]:
            diffs.append("%s %s -> %s" % (p["pump_id"], STATUS_WORD[w], STATUS_WORD[p["status"]]))
    if diffs:
        return "Since %s: %s" % (prev, ", ".join(diffs))
    return "No status changes since %s" % prev


def worst_quality(assessments):
    worst = "SUFFICIENT"
    for a in assessments:
        if QUALITY_RANK.index(a["quality"]) > QUALITY_RANK.index(worst):
            worst = a["quality"]
    return worst


def merged_queue(assessments):
    # Section 4.11: INVESTIGATE by capacity loss (largest first), then WATCH by days open. Nothing is hidden.
    items = []
    for a in assessments:
        for f in a["queue"]:
            items.append({"station_id": a["station_id"], "display_name": a["display_name"], "pump_id": f["pump_id"],
                          "type": f["type"], "status": f["status"], "status_text": STATUS_TEXT[f["status"]],
                          "change_pct": f["change_pct"], "evidence": QUALITY_WORD[a["quality"]], "summary": f["summary"],
                          "opened_on": f["opened_on"], "days_open": f["days_open"], "alert_id": f["alert_id"]})

    def key(i):
        if i["status"] == "INVESTIGATE":
            return (0, i["change_pct"] if i["change_pct"] is not None else 0)  # most negative change first
        return (1, -i["days_open"])
    items.sort(key=key)
    for n, i in enumerate(items):
        i["rank"] = "%d of %d" % (n + 1, len(items))
    return items


def merged_safety(assessments):
    out = []
    for a in assessments:
        for f in a["safety"]:
            if f["type"] == "SOURCE_SILENT":
                text = "Source offline: no data since %s UTC" % ts_text(f["since_utc"])
            else:
                text = "Investigate: %s (SCADA-equivalent; real setpoints unknown)" % f["summary"]
            out.append({"station_id": a["station_id"], "display_name": a["display_name"], "type": f["type"],
                        "status": f["status"], "text": text})
        # Section 10.2: a faulty level sensor makes the high-level check unknown.
        for f in a["queue"]:
            if f["type"] == "SENSOR_FAULT":
                out.append({"station_id": a["station_id"], "display_name": a["display_name"], "type": "HIGH_LEVEL_UNKNOWN",
                            "status": "INSUFFICIENT_EVIDENCE", "text": "High-level check: unknown (level sensor faulty)"})
    return out


def build_tag_values(assessments, timelines, as_of_utc, now_text):
    """assessments: list of StationAssessment dicts. timelines: {station_id: list or None}.
    Returns {relative tag path: value}. Values for DOC_TAGS are JSON strings (poll() decodes them)."""
    day = as_of_utc[0:10]
    prev = prev_day(day)
    out = {}
    first = assessments[0]
    out["_meta/origin"] = first["origin"]
    out["_meta/origin_text"] = ORIGIN_TEXT[first["origin"]]
    out["_meta/data_up_to"] = "Data up to %s UTC" % ts_text(as_of_utc)
    prov = first["provenance"]
    out["_meta/model_version"] = prov["model_version"]
    out["_meta/source_hash"] = prov["source_hash"]
    out["_meta/code_version"] = prov["code_version"]
    q = worst_quality(assessments)
    queue = merged_queue(assessments)
    safety = merged_safety(assessments)
    if q == "SUFFICIENT":
        out["_meta/empty_queue_text"] = "No pumps need attention as of %s." % day
    else:
        out["_meta/empty_queue_text"] = "Nothing flagged, but evidence is %s." % QUALITY_WORD[q]
    out["_queue_all_json"] = json.dumps(queue)
    out["_safety_all_json"] = json.dumps(safety)
    out["_meta/queue_count"] = len(queue)
    out["_meta/safety_count"] = len(safety)
    for a in assessments:
        s = a["station_id"]
        out[s + "/display_name"] = a["display_name"]
        out[s + "/status"] = a["status"]
        out[s + "/quality"] = a["quality"]
        out[s + "/evidence_text"] = "Evidence: %s" % QUALITY_WORD[a["quality"]]
        out[s + "/as_of_utc"] = a["as_of_utc"]
        out[s + "/verdict"] = verdict(a)
        out[s + "/level_sensor_line"] = level_sensor_line(a)
        out[s + "/storm_line"] = storm_line(a)
        out[s + "/changes_line"] = changes_line(a, timelines.get(s), prev)
        out[s + "/explanation"] = a["explanation"]
        out[s + "/safety_json"] = json.dumps(a["safety"])
        out[s + "/queue_json"] = json.dumps(a["queue"])
        for p in a["pumps"]:
            base = "%s/pumps/%s/" % (s, p["pump_id"])
            out[base + "status"] = p["status"]
            out[base + "chip_text"] = "%s %s" % (p["pump_id"], STATUS_WORD[p["status"]])
            out[base + "quality"] = p["quality"]
            out[base + "capacity_change_pct"] = p["capacity_change_pct"]
            out[base + "ci_today"] = p["ci_today"]
            out[base + "ci_baseline"] = p["ci_baseline"]
            out[base + "valid_cycles"] = p["valid_cycles"]
            out[base + "runs"] = p["runs"]
    out["_meta/last_poll_utc"] = now_text
    out["_meta/poll_ok"] = True
    out["_meta/poll_error"] = ""
    return out


def failure_values(message, now_text):
    # On any failure only the status tags change, so tiles keep their last values and "Data up to" keeps its old time.
    return {"_meta/poll_ok": False, "_meta/poll_error": message, "_meta/last_poll_utc": now_text}


# ---------------------------------------------------------------- Ignition-only part (uses system.*)
def poll():
    now_text = system.date.format(system.date.now(), "yyyy-MM-dd HH:mm:ss")
    meta = system.tag.readBlocking([BASE + "/_meta/api_base", BASE + "/_meta/as_of_utc"])
    api_base = str(meta[0].value).rstrip("/")
    as_of = str(meta[1].value)
    try:
        assessments, timelines = [], {}
        prev = prev_day(as_of[0:10])
        for s in STATIONS:
            url = "%s/api/assess?station_id=%s&as_of_utc=%s" % (api_base, s, as_of)
            assessments.append(json.loads(system.net.httpGet(url, 5000, 15000)))
            try:
                turl = "%s/api/timeline?station_id=%s&start=%sT00:00:00Z&end=%s" % (api_base, s, prev, as_of)
                timelines[s] = json.loads(system.net.httpGet(turl, 5000, 15000))
            except Exception:
                timelines[s] = None  # the changes line says "not available"; the tile still renders
        values = build_tag_values(assessments, timelines, as_of, now_text)
    except Exception as e:
        values = failure_values("Dragonfly API: %s" % str(e), now_text)
    paths, vals = [], []
    for rel, v in values.items():
        paths.append("%s/%s" % (BASE, rel))
        vals.append(system.util.jsonDecode(v) if rel.split("/")[-1] in DOC_TAGS else v)
    system.tag.writeBlocking(paths, vals)  # memory tags only


# In the Gateway Event Scripts timer (fixed delay, 60 000 ms), call:  dragonfly_poll.poll()
