"""Checks the gateway script's logic outside Ignition. Run: python3 ignition/tests/test_poll.py
Uses fixtures/ui/assess.json always, and the live API on 127.0.0.1:8000 when it is running (skipped otherwise)."""
import json
import os
import sys
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "gateway"))
sys.path.insert(0, os.path.join(HERE, ".."))
import dragonfly_poll as dp  # noqa: E402
import gen_tags  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
BANNED = ["probability", "will fail", "confirmed", "saved", "prevented", "would have"]


def sample():
    with open(os.path.join(REPO, "fixtures", "ui", "assess.json")) as f:
        return json.load(f)


def live(station, as_of):
    try:
        url = "http://127.0.0.1:8000/api/assess?station_id=%s&as_of_utc=%s" % (station, as_of)
        return json.load(urllib.request.urlopen(url, timeout=10))
    except Exception:
        return None


def finding(status, change, days, pump="P1", ftype="CAPACITY_DROP"):
    return {"alert_id": "REAL:1:%s:%s:2022-06-01" % (pump, ftype), "type": ftype, "pump_id": pump, "status": status, "priority": 1,
            "opened_on": "2022-06-01", "since_utc": "2022-06-01T00:00:00Z", "days_open": days, "observed": None, "expected": None,
            "units": "/h", "change_pct": change, "summary": "s", "possible_causes": [], "inspection": []}


def station(sid, quality="SUFFICIENT", queue=(), safety=(), pumps=None):
    return {"station_id": sid, "display_name": "Wessex " + sid, "as_of_utc": "2022-06-03T00:00:00Z", "origin": "REAL_REPLAY",
            "status": "NORMAL", "quality": quality, "queue": list(queue), "safety": list(safety), "storm": None, "explanation": "x",
            "pumps": pumps or [{"pump_id": "P1", "status": "NORMAL", "quality": "SUFFICIENT", "ci_today": 1.0, "ci_baseline": 1.0,
                                "capacity_change_pct": 0.0, "valid_cycles": 30, "runs": 31}],
            "provenance": {"model_version": "v", "source_hash": "h", "code_version": "c"}}


class Ordering(unittest.TestCase):
    def test_investigate_by_loss_then_watch_by_days(self):
        a = station("1", queue=[finding("WATCH", -10, 2, "P1"), finding("INVESTIGATE", -20, 1, "P2"), finding("WATCH", -9, 5, "P3"),
                                finding("INVESTIGATE", -46, 1, "P4")])
        q = dp.merged_queue([a])
        self.assertEqual([i["pump_id"] for i in q], ["P4", "P2", "P3", "P1"])
        self.assertEqual(q[0]["rank"], "1 of 4")

    def test_empty_queue_text_follows_quality(self):
        v = dp.build_tag_values([station("1")], {}, "2022-06-03T00:00:00Z", "t")
        self.assertEqual(v["_meta/empty_queue_text"], "No pumps need attention as of 2022-06-03.")
        v = dp.build_tag_values([station("1", quality="PARTIAL")], {}, "2022-06-03T00:00:00Z", "t")
        self.assertEqual(v["_meta/empty_queue_text"], "Nothing flagged, but evidence is Partial.")
        self.assertNotIn("All clear", json.dumps(v))


class Lines(unittest.TestCase):
    def test_level_sensor_and_high_level_unknown(self):
        a = station("1", queue=[finding("WATCH", None, 1, None, "SENSOR_FAULT")])
        self.assertEqual(dp.level_sensor_line(a), "Level sensor: Faulty since 2022-06-01 00:00 UTC")
        self.assertEqual(dp.merged_safety([a])[0]["text"], "High-level check: unknown (level sensor faulty)")
        b = station("2", safety=[finding("SOURCE_OFFLINE", None, 1, None, "SOURCE_SILENT")])
        self.assertEqual(dp.level_sensor_line(b), "Level sensor: No data")
        self.assertTrue(dp.merged_safety([b])[0]["text"].startswith("Source offline: no data since 2022-06-01 00:00 UTC"))

    def test_changes_line(self):
        a = station("1", pumps=[{"pump_id": "P1", "status": "WATCH", "quality": "SUFFICIENT", "ci_today": 1, "ci_baseline": 1,
                                 "capacity_change_pct": -5, "valid_cycles": 30, "runs": 31}])
        tl = [{"day": "2022-06-02", "station_status": "NORMAL", "pumps": [{"pump_id": "P1", "status": "NORMAL"}]}]
        self.assertEqual(dp.changes_line(a, tl, "2022-06-02"), "Since 2022-06-02: P1 Normal -> Watch")
        self.assertEqual(dp.changes_line(a, None, "2022-06-02"), "Changes since yesterday: not available")

    def test_prev_day_across_month(self):
        self.assertEqual(dp.prev_day("2022-03-01"), "2022-02-28")

    def test_failure_values_touch_only_status_tags(self):
        self.assertEqual(sorted(dp.failure_values("x", "t")), ["_meta/last_poll_utc", "_meta/poll_error", "_meta/poll_ok"])


class AgainstRealPayloads(unittest.TestCase):
    def check(self, assessments):
        v = dp.build_tag_values(assessments, {}, assessments[0]["as_of_utc"], "now")
        known = set(gen_tags.paths(gen_tags.build()))
        missing = [k for k in v if "Dragonfly/" + k not in known]
        self.assertEqual(missing, [], "script writes tags that the import file does not create")
        text = json.dumps(v).lower()
        for w in BANNED:
            self.assertNotIn(w, text)
        json.loads(v["_queue_all_json"])
        json.loads(v["_safety_all_json"])
        return v

    def test_sample_payload(self):
        self.check([sample()])

    def test_live_api(self):
        a = [live(s, "2022-06-03T00:00:00Z") for s in dp.STATIONS]
        if None in a:
            self.skipTest("API not running on 127.0.0.1:8000")
        v = self.check(a)
        self.assertEqual(v["44371/pumps/P1/status"], "INVESTIGATE")
        self.assertTrue(v["_queue_all_json"].startswith('[{"station_id": "44371"'))
        self.assertEqual(v["_meta/data_up_to"], "Data up to 2022-06-03 00:00 UTC")


class TagFile(unittest.TestCase):
    def test_committed_json_matches_generator(self):
        with open(os.path.join(HERE, "..", "tags", "Dragonfly.json")) as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk, gen_tags.build())

    def test_script_has_no_device_writes(self):
        with open(os.path.join(HERE, "..", "gateway", "dragonfly_poll.py")) as f:
            src = f.read()
        for bad in ["system.opc", "system.device", "httpPost", "httpPut", "system.db"]:
            self.assertNotIn(bad, src)
        self.assertEqual(src.count("system.tag.writeBlocking"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
