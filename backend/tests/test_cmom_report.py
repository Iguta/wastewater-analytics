"""Evidence log: every row carries provenance and blank human fields; 44371's 2022 precursor is in it."""

from backend.app import params
from backend.scripts import cmom_report


def test_evidence_log_rows_for_44371_2022():
    rows = cmom_report.rows_for("44371", 2022, params.load())
    assert rows
    for r in rows:
        assert r["model_version"] and len(r["source_hash"]) == 64
        assert r["acknowledged_by"] == "" and r["outcome"] == ""
    pre = [r for r in rows if r["pump_id"] == "P1" and r["opened_on"].startswith("2022-0")]
    assert any(
        r["opened_on"] <= "2022-06-02" <= r["last_alert_day"] and r["max_status"] == "INVESTIGATE"
        for r in pre
    )
