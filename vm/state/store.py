"""In-memory event store with snapshot/restore and replay.

The store itself is dumb: it appends events and replays them through a
caller-supplied fold function. All domain semantics (how an event changes
state) live in the runtime engine's fold; the store guarantees ordering and
provides checkpoint primitives.

restore() truncates the tail back to a previously taken snapshot. This is an
explicit operator action used for simulation reset / testing — it is NOT a
runtime rollback primitive. Runtime "rollback" is always a compensating
transaction (anti-event appended to the log, never deletion).
"""

from __future__ import annotations

import copy
from typing import Callable


FoldFn = Callable[[dict, dict], dict]


class EventStore:
    def __init__(self) -> None:
        self._events: list[dict] = []
        self._next_seq = 0

    @property
    def events(self) -> tuple[dict, ...]:
        """The log as an immutable snapshot (callers cannot mutate history)."""
        return tuple(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def append(self, event_type: str, payload: dict, principal: str = "caster") -> dict:
        """Append one event; seq numbers are strictly increasing from 0."""
        event = {
            "seq": self._next_seq,
            "type": event_type,
            "principal": principal,
            "payload": copy.deepcopy(payload),
        }
        self._next_seq += 1
        self._events.append(event)
        return copy.deepcopy(event)

    def replay(self, fold: FoldFn, initial: dict | None = None) -> dict:
        """Fold from event 0. Replaying the full log reproduces current state."""
        state: dict = copy.deepcopy(initial) if initial is not None else {}
        for event in self._events:
            state = fold(state, event)
        return state

    def snapshot(self, fold: FoldFn, initial: dict | None = None) -> dict:
        """Capture (seq, folded state) for later restore."""
        return {
            "seq": self._next_seq,
            "state": self.replay(fold, initial),
        }

    def restore(self, snap: dict) -> None:
        """Truncate the log back to a snapshot's seq.

        Operator/testing action only. Runtime compensation must use
        anti-events, never this.
        """
        seq = snap["seq"]
        if not (0 <= seq <= self._next_seq):
            raise ValueError(f"Snapshot seq {seq} out of range")
        self._events = self._events[:seq]
        self._next_seq = seq
