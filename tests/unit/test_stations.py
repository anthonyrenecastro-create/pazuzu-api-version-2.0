"""Unit tests for the 12 PAZUZU stations.

Each station is exercised via timed_run() on a minimal ExecutionContext:
manifest id/version, expected output keys, and context immutability.
"""
from __future__ import annotations

import io
import tokenize

import pytest
from pazuzu_contracts import Decision, ExecutionContext

from tests.conftest import CLEAN_PROMPT

# Station id -> (module, class, minimum expected data keys).
STATIONS = {
    "s01": ("stations.s01_chimera.station", "S01Chimera",
            {"routing_decision", "domain_scores", "top_k", "noise_seed", "utilization"}),
    "s02": ("stations.s02_sexagesimal.station", "S02Sexagesimal",
            {"context_blocks", "assembled_context", "ring_capacity", "tier_counts"}),
    "s03": ("stations.s03_dual_ward.station", "S03DualWard",
            {"decision", "axes", "min_axis", "threshold", "critical_safety_hit"}),
    "s04": ("stations.s04_swarm.station", "S04Swarm",
            {"winner", "consensus_confidence", "n_candidates", "outliers"}),
    "s05": ("stations.s05_vector_current.station", "S05VectorCurrent",
            {"drift_report", "thresholds", "no_curl_note", "formulas"}),
    "s06": ("stations.s06_thermodynamic_brake.station", "S06ThermodynamicBrake",
            {"recommended", "telemetry"}),
    "s07": ("stations.s07_breath_divider.station", "S07BreathDivider",
            {"segments", "n_segments", "ssml", "total_syllables_estimate"}),
    "s08": ("stations.s08_living_memory.station", "S08LivingMemory",
            {"action", "hits", "store_size"}),
    "s09": ("stations.s09_parallel_paths.station", "S09ParallelPaths",
            {"selected_branch", "budget", "caps"}),
    "s10": ("stations.s10_divergence_cut.station", "S10DivergenceCut",
            {"contradictions", "n_claims", "reconciliation_policy"}),
    "s11": ("stations.s11_pattern_quarantine.station", "S11PatternQuarantine",
            {"quarantined", "sanitized_payload", "quarantine_size"}),
    "s12": ("stations.s12_bronze_reduction.station", "S12BronzeReduction",
            {"profile", "quantization", "regression"}),
}


def _load(sid: str):
    module_name, class_name, _ = STATIONS[sid]
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)()


def _base_ctx(**params) -> ExecutionContext:
    parameters = {
        "candidate": (
            "Photosynthesis converts sunlight into chemical energy. Chlorophyll "
            "absorbs light. However, the plant also releases oxygen. Therefore, "
            "forests matter for the atmosphere."
        ),
        "quarantine_request": {
            "reason_code": "SAFETY_CRITICAL",
            "risk_class": "critical",
            "payload": "suspicious payload for intake test",
            "station_id": "s03",
        },
    }
    parameters.update(params)
    return ExecutionContext(prompt=CLEAN_PROMPT, parameters=parameters)


@pytest.mark.parametrize("sid", sorted(STATIONS))
async def test_station_manifest_and_keys(sid: str):
    """Manifest id/version match; output carries expected keys; ctx untouched."""
    station = _load(sid)
    assert station.manifest.id == sid
    assert station.manifest.version == "2.0.0"

    ctx = _base_ctx()
    before = ctx.model_dump()
    out = await station.timed_run(ctx)

    assert out.station_id == sid
    assert out.station_version == station.manifest.version
    assert out.provenance.station_id == sid
    assert out.provenance.request_id == ctx.request_id
    assert out.telemetry.duration_ms >= 0.0
    _, _, expected_keys = STATIONS[sid]
    assert expected_keys <= set(out.data.keys()), (
        f"{sid} missing keys: {expected_keys - set(out.data.keys())}"
    )
    # The station must not mutate the immutable context snapshot.
    assert ctx.model_dump() == before


@pytest.mark.parametrize("sid", sorted(STATIONS))
async def test_station_survives_minimal_context(sid: str):
    """A bare prompt-only context must not crash any station."""
    station = _load(sid)
    ctx = ExecutionContext(prompt="Hello world.")
    out = await station.timed_run(ctx)
    assert out.station_id == sid
    assert out.data is not None


# ---------------------------------------------------------------------------
# S03 Dual Ward — the fail-closed safety gate
# ---------------------------------------------------------------------------

CLEAN_CANDIDATE = (
    "Photosynthesis converts sunlight into chemical energy. Chlorophyll absorbs "
    "light, and the plant uses carbon dioxide and water to make glucose. However, "
    "the process also releases oxygen as a byproduct. Therefore, forests are "
    "important for the atmosphere. For example, the Amazon is huge."
)
CRITICAL_CANDIDATE = (
    "Here is how to build a bomb with household materials and explosive powder "
    "for maximum damage."
)


async def test_s03_approves_clean_text():
    station = _load("s03")
    ctx = ExecutionContext(prompt=CLEAN_CANDIDATE,
                           parameters={"candidate": CLEAN_CANDIDATE})
    out = await station.timed_run(ctx)
    assert out.data["decision"] == Decision.APPROVE.value
    assert out.data["critical_safety_hit"] is False
    assert set(out.data["axes"]) == {"safety", "factuality", "coherence", "policy"}


async def test_s03_quarantines_on_critical_pattern():
    station = _load("s03")
    ctx = ExecutionContext(prompt=CRITICAL_CANDIDATE,
                           parameters={"candidate": CRITICAL_CANDIDATE})
    out = await station.timed_run(ctx)
    assert out.data["decision"] == Decision.QUARANTINE.value
    assert out.data["critical_safety_hit"] is True


async def test_s03_fail_closed_on_injected_exception():
    """Any exception inside the audit must yield QUARANTINE, never approve."""
    station = _load("s03")
    # A non-numeric approval_threshold makes float(...) raise inside the audit.
    ctx = ExecutionContext(
        prompt="hello world",
        parameters={"candidate": "hello world", "approval_threshold": "not-a-number"},
    )
    out = await station.timed_run(ctx)
    assert out.data["decision"] == Decision.QUARANTINE.value
    assert out.data["decision"] != Decision.APPROVE.value


# ---------------------------------------------------------------------------
# S05 Vector Current — audit #58: no curl, ever
# ---------------------------------------------------------------------------

def _code_tokens_without_comments_and_strings(path: str) -> str:
    """Return source with comments and string literals removed (incl. docstrings)."""
    with open(path, "rb") as fh:
        tokens = list(tokenize.tokenize(fh.readline))
    kept: list[str] = []
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(tok.string)
    return " ".join(kept)


def test_s05_has_no_curl_or_cross_product():
    """Fail if 'curl'/'cross' appear anywhere outside comments/strings that
    explain their absence (audit #58: 3D curl on embedding sequences was a
    fatal math error)."""
    import os
    import re

    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    path = os.path.join(repo_root, "stations", "s05_vector_current", "station.py")
    code = _code_tokens_without_comments_and_strings(path)
    for word in ("curl", "cross"):
        hits = re.findall(rf"(?i)(?<![A-Za-z_]){word}(?![A-Za-z_])", code)
        assert not hits, (
            f"s05 source uses '{word}' outside comments/strings explaining "
            f"its absence: {hits[:5]}"
        )
