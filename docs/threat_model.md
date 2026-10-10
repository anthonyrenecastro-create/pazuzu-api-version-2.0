# PAZUZU-API v2.0 — Threat Model (STRIDE)

**Status:** design-stage threat model. Controls marked *(implemented)* exist
in the contracts package. Controls marked *(specified)* are design intent
with no code. Controls marked *(gap)* are acknowledged missing controls.
No penetration testing or security review has been performed (2026-10-09).

## S — Spoofing

| Threat | Control | Status |
|---|---|---|
| Attacker impersonates a tenant/principal | Scoped auth: `ExecutionContext` carries `tenant_id`, `principal`, `scopes`; gateway validates before dispatch | specified (contract fields implemented; gateway scheduled) |
| Attacker forges station outputs to the orchestrator | **Signed internal messages**: every inter-service message carries an Ed25519 signature over `(request_id, station_id, station_version, input_hash, data_hash)`; orchestrator rejects unsigned/mis-signed messages | **gap** — no signing code exists; `Provenance` has no signature field |
| Attacker replays a captured request | Idempotency keys (`ExecutionContext.idempotency_key`) + DPoP-bound tokens at the gateway | specified (field implemented; enforcement scheduled). Note audit #4: DPoP prevents replay but not token exfiltration; **mTLS / payload encryption for the Ingestion Gateway is a gap** |

## T — Tampering

| Threat | Control | Status |
|---|---|---|
| In-transit modification of station outputs | Signed internal messages (above) + TLS between services | **gap** (signing); TLS is deployment config, scheduled |
| Tampering with quarantine records | `QuarantineRecord.history` is append-only; status transitions (`quarantined → under_review → released|destroyed`) validated server-side | specified (model implemented; service scheduled) |
| Tampering with memory records | `MemoryRecord.version` increments on write; no in-place edits — supersede, don't mutate | specified |
| Poisoned provider responses | Watcher independence (S03) + S10 cut on fracture; provider responses tagged `mock: bool` so test doubles can't leak into prod | specified (contract flag implemented) |

## R — Repudiation

| Threat | Control | Status |
|---|---|---|
| "The system never said that" / "I never requested that" | Immutable `Provenance` on every `StationOutput` (`request_id`, `correlation_id`, `station_id`, `station_version`, `input_hash`, `created_at`, `actor`); append-only audit log; S12 reduction trace | **partially implemented**: `Provenance` contract exists; the audit log store and S12 trace assembler are scheduled |
| Operator denies a quarantine decision | `QuarantineRecord.reviewed_by` + `history` entries per transition | specified |

## I — Information disclosure

| Threat | Control | Status |
|---|---|---|
| PII in prompts leaks into logs/telemetry | PII redaction at the Ingestion Gateway before any persistence; redaction policy versioned alongside the plan | **gap** — specified in the brief, no implementation |
| Embedding trajectory exposes semantic geometry to clients (audit #64) | **No embedding trajectory is returned to API clients.** Raw S05 diagnostics are internal-only; `GET /v2/field` is admin-scoped (cf. audit #66) | specified (threat-model requirement; endpoint not built) |
| Provider API keys leak to clients or logs | **Provider keys are server-side only** (`ProviderAdapter` docstring: "Server-side only. Upstream credentials never leave the server."); keys live in env/secret store, never in `data` payloads, never in telemetry `extra` | specified (contract-level guarantee; adapter code scheduled) |
| Tenant cross-read of memory/quarantine | `tenant_id` scoping on `MemoryRecord` and `QuarantineRecord`; queries filtered server-side | specified |

## D — Denial of service

| Threat | Control | Status |
|---|---|---|
| Request floods | Gateway rate limits + per-tenant quotas; bounded worker pools per station (Little's Law — see `architecture/overview.md` §7) | **gap** — no limiter code; gateway scheduled |
| Expensive recursive decomposition (audit #14) | Bounded recursion: max sub-query depth + `ctx.deadline_ms` + `ctx.cancelled` checks on expensive work | **partially implemented**: `deadline_ms`/`cancelled` are contract fields; depth bound unspecified |
| Attacker drives S06 into high-entropy token exhaustion (audit #76) | Per-request token/entropy caps; S06 output clamped to `[T_min, T_max]` | **gap** |
| Slow provider hangs the pipeline | Per-station timeouts (`ExecutionPlan.timeouts_ms`) + fail-closed S3 gate (withhold, don't hang) | specified (contract fields; enforcement scheduled) |
| Memory-exhaustion via S04 fan-out (3–5× KV cache, audit #48) | Cap on concurrent speculative branches per request; branch budget in plan config | **gap** |

## E — Elevation of privilege

| Threat | Control | Status |
|---|---|---|
| Client calls admin endpoints (`/v2/field`, quarantine release, replay with routing records) | Scoped auth: admin-only endpoints require `admin` scope; `principal`/`scopes` validated at gateway *and* re-checked at the service | specified (contract fields; no endpoints built) |
| Replay endpoint used to reverse-engineer routing thresholds (audit #50) | Replay records access-controlled; seed/routing data never exposed to non-admin principals | specified |
| Tenant escapes to another tenant's records | `tenant_id` enforced at the service layer, not just the API layer | specified |

## Residual risks (accepted, documented)

1. **Watcher lag (audit #36):** one-segment-behind scoring means an emitted
   segment cannot be retracted. Fail-closed gates future emissions only.
2. **Correlated failures (audit #1):** Keeper ∩ Watcher independence is
   assumed; shared training corpora correlate failure modes. No mitigation
   specified — the intersection rule's core premise is weaker than claimed.
3. **Watermark spoofability (audit #41):** `ward:degraded` watermarking is an
   internal marker, not a security boundary, if the response schema is
   public.
4. **No mTLS / payload encryption spec** for the Ingestion Gateway (audit #4).
5. **No signed internal messages yet** — the single largest tampering gap.
