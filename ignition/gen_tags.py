"""Writes ignition/tags/Dragonfly.json: the memory-tag tree for Ignition's Tag Browser (Import Tags).
Run from anywhere: python3 ignition/gen_tags.py. The tag list mirrors what gateway/dragonfly_poll.py writes;
tests/test_poll.py fails if the two disagree."""
import json
import os

PUMPS = {"44371": ["P1", "P2"], "45385": ["P1", "P2"], "45078": ["P1", "P2", "P3"]}


def tag(name, dtype, value=None):
    t = {"name": name, "tagType": "AtomicTag", "valueSource": "memory", "dataType": dtype}
    if value is not None:
        t["value"] = value
    return t


def folder(name, tags):
    return {"name": name, "tagType": "Folder", "tags": tags}


def build():
    meta = [tag("as_of_utc", "String", "2022-06-03T00:00:00Z"), tag("api_base", "String", "http://127.0.0.1:8000")]
    meta += [tag(n, "String", "") for n in ["origin", "origin_text", "data_up_to", "model_version", "source_hash",
                                            "code_version", "empty_queue_text", "last_poll_utc", "poll_error"]]
    meta += [tag("poll_ok", "Boolean", True), tag("queue_count", "Int4", 0), tag("safety_count", "Int4", 0)]
    root = [folder("_meta", meta), tag("_queue_all_json", "Document", []), tag("_safety_all_json", "Document", [])]
    for station, pumps in PUMPS.items():
        st = [tag(n, "String", "") for n in ["display_name", "status", "quality", "evidence_text", "as_of_utc", "verdict",
                                             "level_sensor_line", "storm_line", "changes_line", "explanation"]]
        st += [tag("safety_json", "Document", []), tag("queue_json", "Document", [])]
        ps = []
        for p in pumps:
            ps.append(folder(p, [tag("status", "String", ""), tag("chip_text", "String", ""), tag("quality", "String", ""),
                                 tag("capacity_change_pct", "Float4"), tag("ci_today", "Float4"), tag("ci_baseline", "Float4"),
                                 tag("valid_cycles", "Int4", 0), tag("runs", "Int4", 0)]))
        st.append(folder("pumps", ps))
        root.append(folder(station, st))
    return folder("Dragonfly", root)


def paths(node, prefix=""):
    here = prefix + node["name"] if prefix else node["name"]
    if node["tagType"] == "Folder":
        out = []
        for c in node["tags"]:
            out += paths(c, here + "/")
        return out
    return [here]


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tags", "Dragonfly.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(build(), f, indent=2)
        f.write("\n")
