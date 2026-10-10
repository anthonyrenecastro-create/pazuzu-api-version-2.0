"""Telemetry: minimal Prometheus exposition (counters/histograms) + audit registry.

No prometheus_client dependency — a tiny in-process registry is enough for
v1. Metrics exposed at GET /v2/metrics as Prometheus text format.
"""
from __future__ import annotations

import asyncio
import threading
from collections import deque
from typing import Iterable


class Counter:
    def __init__(self, name: str, help_text: str) -> None:
        self.name = name
        self.help = help_text
        self._values: dict[tuple[tuple[str, str], ...], float] = {}
        self._lock = threading.Lock()

    def inc(self, labels: dict[str, str] | None = None, amount: float = 1.0) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def samples(self) -> Iterable[tuple[dict[str, str], float]]:
        with self._lock:
            items = list(self._values.items())
        for key, value in items:
            yield dict(key), value


class Histogram:
    def __init__(self, name: str, help_text: str, buckets: tuple[float, ...] = (5, 25, 100, 500, 2000, 10000)) -> None:
        self.name = name
        self.help = help_text
        self.buckets = buckets
        self._counts: dict[tuple[tuple[str, str], ...], list[float]] = {}
        self._lock = threading.Lock()

    def observe(self, labels: dict[str, str] | None = None, value: float = 0.0) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            bucket_counts = self._counts.setdefault(key, [0.0] * len(self.buckets))
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    bucket_counts[i] += 1.0

    def samples(self) -> Iterable[tuple[dict[str, str], list[float]]]:
        with self._lock:
            items = list(self._counts.items())
        for key, counts in items:
            yield dict(key), counts


requests_total = Counter("pazuzu_requests_total", "Total HTTP requests by method/path/status")
station_duration_ms = Histogram(
    "pazuzu_station_duration_ms", "Station execution duration in milliseconds"
)
s3_decisions_total = Counter("pazuzu_s3_decisions_total", "s03 Dual Ward decisions by outcome")
executions_total = Counter("pazuzu_executions_total", "Executions by final status")
quarantine_total = Counter("pazuzu_quarantine_total", "Quarantine records by risk class")


def _fmt_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    return "{" + ",".join(f'{k}="{v}"' for k, v in sorted(labels.items())) + "}"


def render_prometheus() -> str:
    lines: list[str] = []
    for counter in (requests_total, s3_decisions_total, executions_total, quarantine_total):
        lines.append(f"# HELP {counter.name} {counter.help}")
        lines.append(f"# TYPE {counter.name} counter")
        for labels, value in counter.samples():
            lines.append(f"{counter.name}{_fmt_labels(labels)} {value}")
    h = station_duration_ms
    lines.append(f"# HELP {h.name} {h.help}")
    lines.append(f"# TYPE {h.name} histogram")
    for labels, counts in h.samples():
        cumulative = 0.0
        for bound, count in zip(h.buckets, counts):
            cumulative += count
            lab = dict(labels)
            lab["le"] = str(bound)
            lines.append(f"{h.name}_bucket{_fmt_labels(lab)} {cumulative}")
        lab = dict(labels)
        lab["le"] = "+Inf"
        lines.append(f"{h.name}_bucket{_fmt_labels(lab)} {cumulative}")
    return "\n".join(lines) + "\n"


# -- audit registry -------------------------------------------------------
# Ring buffer of audit entries written by AuditMiddleware. Powers GET /v2/audit.
audit_registry: deque[dict] = deque(maxlen=2000)
_audit_lock = asyncio.Lock()


def audit_summary() -> dict:
    by_status: dict[str, int] = {}
    by_path: dict[str, int] = {}
    by_tenant: dict[str, int] = {}
    entries = list(audit_registry)
    for e in entries:
        by_status[str(e.get("status_code"))] = by_status.get(str(e.get("status_code")), 0) + 1
        by_path[str(e.get("path"))] = by_path.get(str(e.get("path")), 0) + 1
        by_tenant[str(e.get("tenant"))] = by_tenant.get(str(e.get("tenant")), 0) + 1
    return {
        "total": len(entries),
        "by_status": by_status,
        "by_path": by_path,
        "by_tenant": by_tenant,
        "recent": entries[-10:],
    }
