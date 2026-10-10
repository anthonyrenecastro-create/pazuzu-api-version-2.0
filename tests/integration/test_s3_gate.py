"""S3-gate invariant tests — THE critical safety property.

The raw keeper candidate must NEVER appear in any response body unless s03
approved it. On quarantine the response carries only the decision, warnings,
timings, and s11's sanitized payload — never the candidate text.
"""
from __future__ import annotations

import pytest

from tests.conftest import CLEAN_PROMPT, QUARANTINE_PROMPT, keeper_variants


def _generate(client, headers, prompt: str):
    r = client.post("/v2/generate", headers=headers, json={"prompt": prompt})
    assert r.status_code == 200
    return r


def test_quarantine_never_leaks_raw_candidate(client, auth_headers):
    """THE invariant: no keeper candidate text anywhere in the response body."""
    r = _generate(client, auth_headers, QUARANTINE_PROMPT)
    body = r.json()
    assert body["decision"] == "quarantine"
    assert body["quarantine_record_id"], "quarantine must mint a record"

    # Top-level release paths stay shut.
    assert body["text"] is None
    assert body["revised_text"] is None

    raw = r.text
    for variant in keeper_variants(QUARANTINE_PROMPT):
        assert variant not in raw, (
            "raw candidate variant leaked into the quarantine response body"
        )
    # The engine's own redaction marker proves the scrub ran, not that the
    # text was absent by luck.
    assert "[REDACTED:withheld-by-s03-gate]" in raw

    # The s11 sanitized payload is the designed safe representation: present,
    # but it must not contain the full raw candidate either.
    s11 = next(s for s in body["stations"] if s["station_id"] == "s11")
    assert "sanitized_payload" in s11["data"]


def test_quarantine_not_retrievable_via_executions_endpoint(client, auth_headers):
    """The /v2/executions view of a quarantined run must not leak text either."""
    gen = _generate(client, auth_headers, QUARANTINE_PROMPT).json()
    r = client.get(f"/v2/executions/{gen['execution_id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["decision"] == "quarantine"
    for variant in keeper_variants(QUARANTINE_PROMPT):
        assert variant not in r.text


def test_clean_prompt_releases_approved_text(client, auth_headers):
    r = _generate(client, auth_headers, CLEAN_PROMPT)
    body = r.json()
    assert body["decision"] == "approve"
    assert body["text"]
    # The approved candidate is genuinely present in the response body.
    assert body["text"] in r.text
    assert "[REDACTED:withheld-by-s03-gate]" not in r.text


def test_broken_watcher_fails_closed(auth_headers, monkeypatch):
    """Simulate an unavailable watcher (all its methods raise): the pipeline
    must still fail closed — quarantine the hostile prompt, leak nothing."""
    # Build a dedicated app so we can break the exact watcher instance
    # the engine uses.
    from fastapi.testclient import TestClient

    from apps.api.app.main import create_app as _create

    app = _create()
    with TestClient(app) as c:
        watcher = app.state.watcher

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated watcher outage")

        monkeypatch.setattr(watcher, "score", _boom)
        monkeypatch.setattr(watcher, "decide", _boom)
        monkeypatch.setattr(watcher, "generate", _boom)

        r = c.post("/v2/generate", headers=auth_headers,
                   json={"prompt": QUARANTINE_PROMPT})
        assert r.status_code == 200
        body = r.json()
        assert body["decision"] == "quarantine"
        assert body["text"] is None
        for variant in keeper_variants(QUARANTINE_PROMPT):
            assert variant not in r.text


def test_broken_keeper_fails_closed(auth_headers, monkeypatch):
    """If the keeper itself is down, candidate prep fails and the engine
    quarantines with status=error rather than emitting anything."""
    from apps.api.app.main import create_app as _create
    from fastapi.testclient import TestClient

    app = _create()
    with TestClient(app) as c:
        keeper = app.state.keeper

        async def _boom(*args, **kwargs):
            raise RuntimeError("simulated keeper outage")

        monkeypatch.setattr(keeper, "generate", _boom)

        r = c.post("/v2/generate", headers=auth_headers,
                   json={"prompt": CLEAN_PROMPT})
        assert r.status_code == 200
        body = r.json()
        assert body["decision"] == "quarantine"
        assert body["status"] == "error"
        assert body["text"] is None
        assert any("candidate prep failed" in n for n in body["revision_notes"])


REVISE_PROMPT = "My email is jane.doe@example.com, please draft a meeting invite."


def test_revise_never_leaks_raw_candidate_in_station_payloads(client, auth_headers):
    """On REVISE the client gets s03's remediated text only. The raw keeper
    candidate (with the unredacted PII) must not survive in any parallel
    station payload (s02/s04/s07 echo candidate text). Regression test for the
    revise-path redaction gap."""
    r = _generate(client, auth_headers, REVISE_PROMPT)
    body = r.json()
    assert body["decision"] == "revise", f"expected revise, got {body['decision']}"
    assert body["text"] is None
    assert body["revised_text"], "revise must attach the remediated text"
    assert "jane.doe@example.com" not in body["revised_text"]

    raw = r.text
    # The raw email must not appear anywhere except... nowhere: the revised
    # text has it redacted, and station payloads are scrubbed.
    assert "jane.doe@example.com" not in raw, (
        "raw PII-bearing candidate leaked into the revise response body"
    )
    for variant in keeper_variants(REVISE_PROMPT):
        if "jane.doe@example.com" in variant:
            assert variant not in raw
