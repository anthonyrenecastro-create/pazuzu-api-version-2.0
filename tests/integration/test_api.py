"""Integration tests for the PAZUZU-API v2.0 HTTP surface (TestClient)."""
from __future__ import annotations

import pytest

from tests.conftest import CLEAN_PROMPT, QUARANTINE_PROMPT


def test_health_live_public(client):
    r = client.get("/health/live")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "live"
    assert body["service"] == "pazuzu-api"


def test_generate_clean_prompt_approves(client, auth_headers):
    r = client.post("/v2/generate", headers=auth_headers,
                    json={"prompt": CLEAN_PROMPT})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "approve"
    assert body["status"] == "completed"
    assert body["text"], "approved text must be present"
    assert body["execution_id"]
    assert body["quarantine_record_id"] is None
    station_ids = {s["station_id"] for s in body["stations"]}
    assert {"s01", "s02", "s03", "s04", "s05", "s06", "s07", "s10"} <= station_ids


def test_generate_returns_execution_record(client, auth_headers):
    gen = client.post("/v2/generate", headers=auth_headers,
                      json={"prompt": CLEAN_PROMPT}).json()
    r = client.get(f"/v2/executions/{gen['execution_id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["execution_id"] == gen["execution_id"]
    assert r.json()["decision"] == "approve"


def test_generate_unknown_execution_404(client, auth_headers):
    r = client.get("/v2/executions/does-not-exist", headers=auth_headers)
    assert r.status_code == 404


def test_stream_emits_approved_and_completed(client, auth_headers):
    r = client.post("/v2/stream", headers=auth_headers,
                    json={"prompt": CLEAN_PROMPT})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    assert r.headers["X-Decision-Event"] == "approved"
    assert "event: approved" in r.text
    assert "event: completed" in r.text


def test_stream_quarantine_withholds_candidate(client, auth_headers):
    from tests.conftest import keeper_variants

    r = client.post("/v2/stream", headers=auth_headers,
                    json={"prompt": QUARANTINE_PROMPT})
    assert r.status_code == 200
    assert r.headers["X-Decision-Event"] == "withheld"
    assert "event: withheld" in r.text
    assert "event: completed" in r.text
    assert "event: candidate" not in r.text
    for variant in keeper_variants(QUARANTINE_PROMPT):
        assert variant not in r.text


def test_list_stations_returns_12_manifests(client, auth_headers):
    r = client.get("/v2/stations", headers=auth_headers)
    assert r.status_code == 200
    stations = r.json()["stations"]
    assert len(stations) == 12
    ids = {s["id"] for s in stations}
    assert ids == {f"s{i:02d}" for i in range(1, 13)}
    for s in stations:
        assert s["version"] == "2.0.0"
        assert s["name"]


def test_get_single_station(client, auth_headers):
    r = client.get("/v2/stations/s03", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == "s03"
    r = client.get("/v2/stations/s99", headers=auth_headers)
    assert r.status_code == 404


def test_pipeline_validate_ok(client, auth_headers):
    from pazuzu_contracts import ExecutionPlan

    r = client.post("/v2/pipeline/validate", headers=auth_headers,
                    json=ExecutionPlan().model_dump())
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["errors"] == []


def test_pipeline_validate_rejects_plan_without_s03(client, auth_headers):
    from pazuzu_contracts import ExecutionPlan

    plan = ExecutionPlan(critical_path=["s01", "s02"])
    r = client.post("/v2/pipeline/validate", headers=auth_headers,
                    json=plan.model_dump())
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert any("s03" in e for e in body["errors"])


def test_memory_crud(client, auth_headers):
    created = client.post(
        "/v2/memory", headers=auth_headers,
        json={"kind": "fact", "content": {"k": "v"}}).json()
    assert created["id"]
    assert created["kind"] == "fact"

    listed = client.get("/v2/memory", headers=auth_headers).json()
    assert listed["count"] >= 1
    assert any(rec["id"] == created["id"] for rec in listed["records"])

    deleted = client.delete(f"/v2/memory/{created['id']}", headers=auth_headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == created["id"]

    again = client.delete(f"/v2/memory/{created['id']}", headers=auth_headers)
    assert again.status_code == 404


def test_quarantine_list_and_review_flow(client, auth_headers):
    gen = client.post("/v2/generate", headers=auth_headers,
                      json={"prompt": QUARANTINE_PROMPT}).json()
    assert gen["decision"] == "quarantine"
    record_id = gen["quarantine_record_id"]
    assert record_id

    listed = client.get("/v2/quarantine", headers=auth_headers).json()
    assert listed["count"] >= 1
    assert any(r["id"] == record_id for r in listed["records"])

    review = client.post(f"/v2/quarantine/{record_id}/review",
                         headers=auth_headers,
                         json={"action": "start_review"}).json()
    assert review["status"] == "under_review"

    released = client.post(f"/v2/quarantine/{record_id}/review",
                           headers=auth_headers,
                           json={"action": "release"}).json()
    assert released["status"] == "released"
    assert released["reviewed_by"]


def test_quarantine_invalid_transition_422(client, auth_headers):
    gen = client.post("/v2/generate", headers=auth_headers,
                      json={"prompt": QUARANTINE_PROMPT}).json()
    record_id = gen["quarantine_record_id"]
    # release straight from 'quarantined' skips under_review -> invalid.
    r = client.post(f"/v2/quarantine/{record_id}/review", headers=auth_headers,
                    json={"action": "release"})
    assert r.status_code == 422


def test_replay_returns_same_execution_reference(client, auth_headers):
    gen = client.post("/v2/generate", headers=auth_headers,
                      json={"prompt": CLEAN_PROMPT}).json()
    original_id = gen["execution_id"]
    r = client.post("/v2/replay", headers=auth_headers,
                    json={"execution_id": original_id})
    assert r.status_code == 200
    body = r.json()
    assert body["replay_of"] == original_id
    assert body["execution_id"] != original_id
    assert body["decision"] == gen["decision"]


def test_provenance_lists_station_provenance(client, auth_headers):
    gen = client.post("/v2/generate", headers=auth_headers,
                      json={"prompt": CLEAN_PROMPT}).json()
    r = client.get(f"/v2/provenance/{gen['execution_id']}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["execution_id"] == gen["execution_id"]
    assert len(body["provenance"]) >= 8
    for entry in body["provenance"]:
        assert entry["station_id"]
        assert entry["station_version"]
        assert entry["request_id"]


def test_verify_runs_s03_gate(client, auth_headers):
    r = client.post("/v2/verify", headers=auth_headers,
                    json={"text": "The sky is blue and water is wet."})
    assert r.status_code == 200
    body = r.json()
    assert body["station"]["id"] == "s03"
    assert body["decision"] in ("approve", "revise", "reject", "quarantine")
