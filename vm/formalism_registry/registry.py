"""Formalism registry: lookup and reporting over registry entries.

Every formalism from the source notes that the VM touches is recorded here
with its honesty status. Use summary() for audits.
"""

from __future__ import annotations

from .entries import ENTRIES

STATUSES = (
    "IMPLEMENTED_TESTED",
    "IMPLEMENTED_UNVERIFIED",
    "REVIEW_REQUIRED",
    "NOT_IMPLEMENTED",
)


def _check(entry: dict) -> None:
    required = {
        "id", "title", "source_equation", "symbols", "units",
        "computational_interpretation", "assumptions", "limitations",
        "implementation_ref", "verification_status", "analogy",
    }
    missing = required - set(entry)
    if missing:
        raise ValueError(f"Entry {entry.get('id')!r} missing fields: {missing}")
    if entry["verification_status"] not in STATUSES:
        raise ValueError(
            f"Entry {entry['id']!r} bad status {entry['verification_status']!r}"
        )


for _e in ENTRIES:
    _check(_e)

_IDS = {e["id"]: e for e in ENTRIES}
if len(_IDS) != len(ENTRIES):
    raise ValueError("Duplicate formalism registry ids")


def get(entry_id: str) -> dict | None:
    """Fetch one entry by id, or None."""
    return _IDS.get(entry_id)


def by_status(status: str) -> list[dict]:
    """All entries with a given verification_status."""
    if status not in STATUSES:
        raise ValueError(f"Unknown status {status!r}")
    return [e for e in ENTRIES if e["verification_status"] == status]


def analogies() -> list[dict]:
    """Entries explicitly marked as analogies (not literal claims)."""
    return [e for e in ENTRIES if e["analogy"]]


def summary() -> dict:
    """Counts per status plus the id lists, for audit reporting."""
    return {
        "total": len(ENTRIES),
        "by_status": {
            s: [e["id"] for e in ENTRIES if e["verification_status"] == s]
            for s in STATUSES
        },
        "analogies": [e["id"] for e in ENTRIES if e["analogy"]],
    }
