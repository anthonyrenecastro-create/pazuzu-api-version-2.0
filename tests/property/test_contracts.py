"""Property-style tests for the core contract invariants."""
from __future__ import annotations

import pytest
from pydantic import ValidationError
from pazuzu_contracts import ExecutionContext, Provenance, StationOutput

from tests.conftest import CLEAN_PROMPT


def _output(station_id: str = "s03") -> StationOutput:
    return StationOutput(
        station_id=station_id,
        station_version="2.0.0",
        data={"decision": "approve"},
        provenance=Provenance(
            request_id="r1",
            correlation_id="c1",
            station_id=station_id,
            station_version="2.0.0",
        ),
    )


def test_station_output_is_frozen():
    """Attribute assignment on a StationOutput raises (frozen model)."""
    out = _output()
    with pytest.raises(ValidationError):
        out.station_id = "s04"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        out.status = "bogus"  # type: ignore[misc]
    # Failed mutation leaves the original untouched.
    assert out.station_id == "s03"


def test_execution_context_is_frozen():
    ctx = ExecutionContext(prompt=CLEAN_PROMPT)
    with pytest.raises(ValidationError):
        ctx.prompt = "mutated"  # type: ignore[misc]
    assert ctx.prompt == CLEAN_PROMPT


def test_with_output_does_not_mutate_original():
    """with_output returns a NEW context; the original keeps zero outputs."""
    ctx = ExecutionContext(prompt=CLEAN_PROMPT)
    out = _output("s03")
    assert ctx.station_outputs == {}

    ctx2 = ctx.with_output(out)
    assert ctx.station_outputs == {}, "original context must be unmodified"
    assert set(ctx2.station_outputs) == {"s03"}
    assert ctx2.station_outputs["s03"].station_id == "s03"

    # Chaining accumulates without aliasing earlier snapshots.
    ctx3 = ctx2.with_output(_output("s05"))
    assert set(ctx2.station_outputs) == {"s03"}
    assert set(ctx3.station_outputs) == {"s03", "s05"}


def test_station_output_round_trips_through_json():
    out = _output("s07")
    serialized = out.model_dump_json()
    restored = StationOutput.model_validate_json(serialized)
    assert restored == out
    assert restored.provenance.request_id == "r1"
    assert restored.data == {"decision": "approve"}


def test_execution_context_round_trips_through_json():
    ctx = ExecutionContext(prompt=CLEAN_PROMPT).with_output(_output("s01"))
    restored = ExecutionContext.model_validate_json(ctx.model_dump_json())
    assert restored == ctx
    assert restored.station_outputs["s01"].station_id == "s01"


def test_provenance_carries_request_identity():
    ctx = ExecutionContext(prompt=CLEAN_PROMPT)
    out = _output("s02")
    assert out.provenance.request_id != ctx.request_id  # distinct by construction
    derived = Provenance(
        request_id=ctx.request_id,
        correlation_id=ctx.correlation_id,
        station_id="s02",
        station_version="2.0.0",
    )
    assert derived.request_id == ctx.request_id
    assert derived.correlation_id == ctx.correlation_id
