"""In-memory quarantine records + admin review workflow.

Lifecycle: quarantined -> under_review -> released | destroyed.
Transitions are validated; every transition appends to record.history.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from pazuzu_contracts import QuarantineRecord

from .. import telemetry as _telemetry

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "quarantined": {"under_review", "destroyed"},
    "under_review": {"released", "destroyed"},
    "released": set(),
    "destroyed": set(),
}


class ReviewActionError(ValueError):
    """Raised when a review transition is invalid."""


class QuarantineStore:
    def __init__(self) -> None:
        self._data: dict[str, QuarantineRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, record: QuarantineRecord) -> QuarantineRecord:
        async with self._lock:
            self._data[record.id] = record
            _telemetry.quarantine_total.inc({"risk_class": record.risk_class})
            return record

    async def get(self, record_id: str) -> QuarantineRecord | None:
        async with self._lock:
            return self._data.get(record_id)

    async def list(self, status: str | None = None) -> list[QuarantineRecord]:
        async with self._lock:
            records = list(self._data.values())
            if status:
                records = [r for r in records if r.status == status]
            return sorted(records, key=lambda r: r.created_at, reverse=True)

    async def review(self, record_id: str, action: str, reviewer: str) -> QuarantineRecord:
        """Apply an admin review action.

        Actions: 'start_review' (quarantined->under_review),
                 'release'     (under_review->released),
                 'destroy'     (quarantined|under_review->destroyed).
        """
        action_to_status = {
            "start_review": "under_review",
            "release": "released",
            "destroy": "destroyed",
        }
        if action not in action_to_status:
            raise ReviewActionError(f"Unknown review action '{action}'")
        target = action_to_status[action]
        async with self._lock:
            rec = self._data.get(record_id)
            if rec is None:
                raise ReviewActionError(f"Quarantine record '{record_id}' not found")
            if target not in _VALID_TRANSITIONS[rec.status]:
                raise ReviewActionError(
                    f"Invalid transition {rec.status} -> {target} for record '{record_id}'"
                )
            updated = rec.model_copy(
                update={
                    "status": target,
                    "reviewed_by": reviewer,
                    "history": rec.history
                    + [
                        {
                            "action": action,
                            "from": rec.status,
                            "to": target,
                            "reviewer": reviewer,
                            "at": datetime.now(timezone.utc).isoformat(),
                        }
                    ],
                }
            )
            self._data[record_id] = updated
            return updated
