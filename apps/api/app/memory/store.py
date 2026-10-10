"""In-memory MemoryRecord store with tenant scoping, pinning, and expiry.

SCHEDULED (v2 roadmap): migrate to Postgres (table memory_records with
tenant_id, kind, content JSONB, embedding_ref, pinned, created_at,
expires_at, version). The async interface here is intentionally DB-shaped so
the migration is a drop-in: create/get/list/delete + a background expiry
sweeper become SQL operations with the same signatures.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from pazuzu_contracts import MemoryRecord


class MemoryStore:
    def __init__(self, sweep_interval_s: float = 30.0) -> None:
        self._data: dict[str, dict[str, MemoryRecord]] = {}
        self._lock = asyncio.Lock()
        self._sweep_interval_s = sweep_interval_s
        self._reaper_task: asyncio.Task | None = None

    async def create(self, record: MemoryRecord) -> MemoryRecord:
        async with self._lock:
            self._data.setdefault(record.tenant_id, {})[record.id] = record
            return record

    async def get(self, tenant_id: str, record_id: str) -> MemoryRecord | None:
        async with self._lock:
            rec = self._data.get(tenant_id, {}).get(record_id)
            if rec is not None and self._is_expired(rec):
                del self._data[tenant_id][record_id]
                return None
            return rec

    async def list(self, tenant_id: str, kind: str | None = None) -> list[MemoryRecord]:
        async with self._lock:
            records = list(self._data.get(tenant_id, {}).values())
            live = [r for r in records if not self._is_expired(r)]
            if kind:
                live = [r for r in live if r.kind == kind]
            return sorted(live, key=lambda r: r.created_at, reverse=True)

    async def delete(self, tenant_id: str, record_id: str) -> bool:
        async with self._lock:
            bucket = self._data.get(tenant_id, {})
            if record_id in bucket:
                del bucket[record_id]
                return True
            return False

    @staticmethod
    def _is_expired(rec: MemoryRecord) -> bool:
        if rec.pinned or rec.expires_at is None:
            return False
        return rec.expires_at <= datetime.now(timezone.utc)

    async def _sweep(self) -> None:
        async with self._lock:
            for tenant, bucket in self._data.items():
                expired = [rid for rid, rec in bucket.items() if self._is_expired(rec)]
                for rid in expired:
                    del bucket[rid]

    async def _reaper(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._sweep_interval_s)
                await self._sweep()
        except asyncio.CancelledError:
            pass

    def start_reaper(self) -> None:
        if self._reaper_task is None:
            self._reaper_task = asyncio.create_task(self._reaper())

    async def stop_reaper(self) -> None:
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass
            self._reaper_task = None
