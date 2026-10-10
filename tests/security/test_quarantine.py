"""Security tests for the quarantine lifecycle."""
from __future__ import annotations

import pytest

from tests.conftest import QUARANTINE_PROMPT, keeper_variants


@pytest.fixture()
def quarantined(client, auth_headers):
    """Run a quarantine-triggering prompt; return (client, record_id)."""
    gen = client.post("/v2/generate", headers=auth_headers,
                      json={"prompt": QUARANTINE_PROMPT}).json()
    assert gen["decision"] == "quarantine"
    return client, auth_headers, gen["quarantine_record_id"], gen["execution_id"]


def test_quarantine_record_lists_without_payload(quarantined):
    client, headers, record_id, _ = quarantined
    r = client.get("/v2/quarantine", headers=headers)
    assert r.status_code == 200
    records = {rec["id"]: rec for rec in r.json()["records"]}
    assert record_id in records
    rec = records[record_id]
    assert rec["status"] == "quarantined"
    # The record carries a payload *reference* (hash), never the payload.
    assert "payload_ref" in rec
    assert "payload" not in rec or rec.get("payload") is None
    for variant in keeper_variants(QUARANTINE_PROMPT):
        assert variant not in r.text


def test_quarantine_review_requires_admin_scope(limited_client):
    """Non-admin principals cannot review quarantine records (403)."""
    r = limited_client.get(
        "/v2/quarantine", headers={"Authorization": "Bearer test-token"}
    )
    assert r.status_code == 403


def test_review_transitions_validated(quarantined):
    client, headers, record_id, _ = quarantined

    # Unknown record -> 422.
    r = client.post("/v2/quarantine/nope/review", headers=headers,
                    json={"action": "start_review"})
    assert r.status_code == 422

    # Invalid transition: release directly from quarantined -> 422.
    r = client.post(f"/v2/quarantine/{record_id}/review", headers=headers,
                    json={"action": "release"})
    assert r.status_code == 422

    # Valid: start_review -> under_review -> release.
    r = client.post(f"/v2/quarantine/{record_id}/review", headers=headers,
                    json={"action": "start_review"})
    assert r.status_code == 200
    assert r.json()["status"] == "under_review"

    # Terminal states reject further transitions.
    r = client.post(f"/v2/quarantine/{record_id}/review", headers=headers,
                    json={"action": "destroy"})
    assert r.status_code == 200
    assert r.json()["status"] == "destroyed"
    r = client.post(f"/v2/quarantine/{record_id}/review", headers=headers,
                    json={"action": "start_review"})
    assert r.status_code == 422


def test_released_payload_requires_admin(quarantined):
    """Only an admin-scoped principal can move a record to released, and the
    release is recorded with reviewer attribution + history."""
    client, headers, record_id, _ = quarantined
    client.post(f"/v2/quarantine/{record_id}/review", headers=headers,
                json={"action": "start_review"})
    r = client.post(f"/v2/quarantine/{record_id}/review", headers=headers,
                    json={"action": "release"})
    assert r.status_code == 200
    rec = r.json()
    assert rec["status"] == "released"
    assert rec["reviewed_by"], "release must attribute the reviewer"
    assert any(h.get("to") == "released" for h in rec["history"])


def test_quarantined_payload_not_retrievable_via_executions(quarantined):
    client, headers, _, execution_id = quarantined
    r = client.get(f"/v2/executions/{execution_id}", headers=headers)
    assert r.status_code == 200
    payload = r.json()
    assert payload["text"] is None
    assert payload["revised_text"] is None
    for variant in keeper_variants(QUARANTINE_PROMPT):
        assert variant not in r.text
