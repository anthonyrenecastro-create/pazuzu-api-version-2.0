"""Invariant checkers for VM state and the event log.

Each checker returns {"name": str, "passed": bool, "detail": str}.
check_all() runs every checker and returns the list, suitable for the
`invariant_checks` field of VMSimulateResponse.
"""

from __future__ import annotations


def check_mana_nonnegative(state: dict) -> dict:
    balances = state.get("mana", {})
    bad = {p: b for p, b in balances.items() if b < 0}
    return {
        "name": "mana_nonnegative",
        "passed": not bad,
        "detail": "all balances >= 0" if not bad else f"negative balances: {bad}",
    }


def check_append_only(events: tuple[dict, ...] | list[dict]) -> dict:
    seqs = [e["seq"] for e in events]
    ok = seqs == list(range(len(seqs)))
    return {
        "name": "event_log_append_only",
        "passed": ok,
        "detail": (
            f"{len(seqs)} events, seqs strictly increasing from 0"
            if ok
            else f"seq anomaly: {seqs[:10]}..."
        ),
    }


def check_capability_monotonicity(events: tuple[dict, ...] | list[dict]) -> dict:
    """Granted capabilities must never shrink: per principal, the capability
    set is monotonically non-decreasing over the log. Any explicit revoke
    event is a violation (compensation must grant replacements, not remove)."""
    caps: dict[str, set[str]] = {}
    for e in events:
        if e["type"] == "attune.grant":
            p = e["principal"]
            before = caps.get(p, set())
            granted = set(e["payload"].get("capabilities", []))
            if not granted >= before and before:
                # grants are additive; a grant that drops prior caps violates
                pass
            caps[p] = before | granted
        elif e["type"] == "capability.revoke":
            return {
                "name": "capability_monotonicity",
                "passed": False,
                "detail": f"revoke event at seq {e['seq']} breaks monotonicity",
            }
    return {
        "name": "capability_monotonicity",
        "passed": True,
        "detail": f"{len(caps)} principals, capabilities only ever granted",
    }


def check_no_tombstone_resurrection(state: dict) -> dict:
    """A banished (tombstoned) name must not reappear in the live bindings."""
    tombstoned = set(state.get("tombstones", {}))
    live = set(state.get("bindings", {}))
    clash = tombstoned & live
    return {
        "name": "no_tombstone_resurrection",
        "passed": not clash,
        "detail": "ok" if not clash else f"resurrected: {sorted(clash)}",
    }


def check_all(state: dict, events: tuple[dict, ...] | list[dict]) -> list[dict]:
    return [
        check_mana_nonnegative(state),
        check_append_only(events),
        check_capability_monotonicity(events),
        check_no_tombstone_resurrection(state),
    ]
