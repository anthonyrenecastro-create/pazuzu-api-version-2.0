"""State package: event store and invariant checkers."""

from .store import EventStore
from .invariants import check_all

__all__ = ["EventStore", "check_all"]
