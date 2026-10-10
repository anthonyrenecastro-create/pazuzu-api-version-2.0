"""S08 Living Memory — event memory store (retrieval, not learning).

Contract
--------
Wraps the memory-store contract as an in-memory, per-tenant list of
``MemoryRecord`` objects. Actions are selected via
``ctx.parameters["memory_action"]``:

- ``record``: append a record (``record`` = {kind, content, pinned,
  ttl_seconds}). Expiry computed from ttl.
- ``pin``: pin an existing record by ``record_id``.
- ``expire``: sweep and remove expired, unpinned records; report counts.
- ``retrieve``: keyword-overlap retrieval over record content; returns
  ranked records. This is RETRIEVAL (lookup of stored events), not
  learning.
- ``lora_train``: explicitly NOT_IMPLEMENTED — no weight updates happen
  in this station; returns status note "scheduled" (a fine-tuning
  pipeline is out of scope for the request path).

Retrieval vs learning (documented): retrieval returns stored records
ranked by lexical overlap; learning would change model parameters and
does not occur here. Nothing in this station trains, fine-tunes, or
otherwise modifies a model.

Assumptions
-----------
- Store is process-local (instance attribute), keyed by
  ``ctx.tenant_id``. Durable deployments must replace with a real backend.
- Parameters: ``memory_action`` (default "retrieve"), ``query``,
  ``record``, ``record_id``, ``top_k`` (5), ``memory_seed_records``.

Known limitations
-----------------
- In-memory only: records vanish on restart; no cross-process sharing.
- Keyword retrieval is lexical; no semantic search, no ranking model.
- Expiry sweep only runs when the ``expire`` action is invoked.
- No access control beyond tenant keying; no encryption at rest.
"""
from __future__ import annotations

import time
from datetime import timedelta

from pazuzu_contracts import (
    ExecutionContext,
    MemoryRecord,
    Station,
    StationManifest,
    StationOutput,
    StationStatus,
)

_LORA_STATUS = {
    "implemented": False,
    "status": "scheduled",
    "note": (
        "LoRA fine-tuning is NOT_IMPLEMENTED in the request path. "
        "Parameter updates are out of scope here; memory in this station "
        "means stored event records, retrievable by keyword."
    ),
}


def _record_text(rec: MemoryRecord) -> str:
    return str(rec.content)


class S08LivingMemory(Station):
    """In-memory event memory: record / pin / expire / retrieve."""

    manifest = StationManifest(
        id="s08",
        name="Living Memory",
        version="2.0.0",
        critical_path=False,
        description="In-memory tenant-keyed MemoryRecord store with keyword "
                    "retrieval. LoRA path explicitly NOT_IMPLEMENTED.",
    )

    def __init__(self) -> None:
        # Process-local store: tenant_id -> [MemoryRecord]. Telemetry-grade
        # persistence only; replace with a durable backend in production.
        self._store: dict[str, list[MemoryRecord]] = {}

    def _tenant_store(self, tenant: str) -> list[MemoryRecord]:
        return self._store.setdefault(tenant, [])

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        params = ctx.parameters or {}
        action = str(params.get("memory_action", "retrieve")).lower()
        store = self._tenant_store(ctx.tenant_id)

        for seed in params.get("memory_seed_records", []):
            store.append(MemoryRecord(
                tenant_id=ctx.tenant_id,
                kind=seed.get("kind", "event"),
                content=seed.get("content", {}),
                pinned=bool(seed.get("pinned", False)),
            ))

        result: dict = {"action": action}
        status = StationStatus.OK
        warnings: list[str] = []

        if action == "record":
            spec = params.get("record", {})
            ttl = spec.get("ttl_seconds")
            rec = MemoryRecord(
                tenant_id=ctx.tenant_id,
                kind=spec.get("kind", "event"),
                content=spec.get("content", {}),
                pinned=bool(spec.get("pinned", False)),
                expires_at=(MemoryRecord().created_at + timedelta(seconds=ttl)) if ttl else None,
            )
            store.append(rec)
            result["record"] = rec.model_dump(mode="json")

        elif action == "pin":
            rid = params.get("record_id")
            rec = next((r for r in store if r.id == rid), None)
            if rec is None:
                status = StationStatus.FAILED
                result["error"] = f"record {rid} not found"
            else:
                # MemoryRecord is a pydantic model (mutable here, store-local).
                object.__setattr__(rec, "pinned", True)
                result["record"] = rec.model_dump(mode="json")

        elif action == "expire":
            now = MemoryRecord().created_at
            before = len(store)
            kept = [r for r in store
                    if r.pinned or r.expires_at is None or r.expires_at > now]
            expired = before - len(kept)
            self._store[ctx.tenant_id] = kept
            result.update({"expired": expired, "remaining": len(kept)})

        elif action == "retrieve":
            query = str(params.get("query", ctx.prompt or ""))
            q_terms = {t.lower() for t in query.split()}
            top_k = max(1, int(params.get("top_k", 5)))
            scored = []
            for r in store:
                terms = {t.lower() for t in _record_text(r).split()}
                overlap = len(q_terms & terms)
                scored.append((overlap, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            hits = [r.model_dump(mode="json") for s, r in scored[:top_k] if s > 0]
            result.update({
                "query": query,
                "hits": hits,
                "n_hits": len(hits),
                "store_size": len(store),
                "retrieval_note": (
                    "Keyword-overlap RETRIEVAL of stored events. No model "
                    "parameters were read or modified; this is lookup, not learning."
                ),
            })

        elif action == "lora_train":
            # Explicitly NOT_IMPLEMENTED — scheduled, out of request path.
            result["lora"] = _LORA_STATUS
            warnings.append("lora_train requested: NOT_IMPLEMENTED (status: scheduled)")

        else:
            status = StationStatus.FAILED
            result["error"] = f"unknown memory_action '{action}'"

        result["lora_path"] = _LORA_STATUS
        result["store_size"] = len(self._store.get(ctx.tenant_id, []))
        return self.output(
            ctx, result, status=status, warnings=warnings,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
