# PAZUZU-API v2.0 — System Architecture Overview

**Status:** Design documented. Implementation of the pipeline, services, and API
is **scheduled**; only the shared contracts package
(`packages/contracts/python/pazuzu_contracts`) exists as code (2026-10-09).
Everything below marked *(scheduled)* has no implementation yet. Anything marked
*(implemented)* exists in the contracts package and can be verified by reading it.

> **Note on the topology diagram.** The original §1 ASCII topology was not among
> the supplied source materials. The diagram below is **reconstructed** from the
> design brief (ingestion gateway → 12-station pipeline → stream/telemetry/safety
> planes) and the `ExecutionPlan` contract defaults in
> `packages/contracts/python/pazuzu_contracts/models.py`. It is faithful to the
> brief but is not a verbatim copy of the source diagram.

## 1. Topology

```
                            ┌───────────────────────────────┐
                            │      Ingestion Gateway        │  (services/gateway) — scheduled
                            │  auth · rate limit · schema   │  Provider keys live here only.
                            │  validation · PII redaction   │  They never leave the server.
                            └───────────────┬───────────────┘
                                            │
                            ┌───────────────┴───────────────┐
                            │          Orchestrator         │  (services/orchestrator) — scheduled
                            │  plan version N · immutable   │  Owns the merge/reconciliation
                            │  ExecutionContext snapshots   │  of parallel streams (see §4).
                            └───────────────┬───────────────┘
                                            │
        ┌───────────────────────┬───────────┴───────────┬───────────────────────┐
        │  CRITICAL PATH        │  PARALLEL STREAMS     │  BACKGROUND LOOPS     │
        │  sequential, blocking │  concurrent, advisory │  async, non-blocking  │
        │                       │                       │                       │
        │  S01 Chimera Gate     │  S04 Swarm Agreement  │  S08 Living Memory    │
        │    │                  │  S05 Vector Current   │  S12 Bronze Reduction │
        │  S02 Sexagesimal Turn │  S07 Breath Divider   │                       │
        │    │                  │  S10 Divergence Cut   │  (S09 placement:      │
        │  S03 Dual Ward        │                       │   UNSPECIFIED — see   │
        │    │  ┌───────────────┤  reconcile:           │   §3 open question)   │
        │  S06 Thermo Brake │ fail-closed             │  s10 > s05 > s04 > s07 │
        │    │  │ S3 gate       │  (precedence)         │                       │
        │  S11 Pattern      └───┘                       │                       │
        │      Quarantine   │                           │                       │
        └──────┼────────────┴───────────┬───────────────┴───────────────────────┘
               │                       │
   ┌───────────┴────────┐  ┌───────────┴──────────┐  ┌─────────────────────────┐
   │  STREAM PLANE      │  │  TELEMETRY PLANE     │  │  SAFETY PLANE           │
   │  (SSE) — scheduled │  │  — scheduled         │  │  — scheduled            │
   │  candidate/approved│  │  per-station metrics │  │  services/verifier      │
   │  withheld/revised/ │  │  duration, tokens,   │  │  services/quarantine    │
   │  rejected/completed│  │  cost, t-digests     │  │  S11 quarantine handoff │
   │  error             │  │                      │  │  audit log              │
   └────────────────────┘  └──────────────────────┘  └─────────────────────────┘
```

Supporting services (all **scheduled**, dirs present but empty):

| Service | Dir | Role |
|---|---|---|
| gateway | `services/gateway` | Ingress: auth, rate limits, schema validation, PII redaction |
| orchestrator | `services/orchestrator` | Plan execution, context snapshots, reconciliation |
| providers | `services/providers` | Upstream LLM adapters (server-side keys only) |
| telemetry | `services/telemetry` | Metrics ingest, t-digest merge, EVT p99 |
| verifier | `services/verifier` | Replay verification, invariant checks |
| quarantine | `services/quarantine` | Quarantine store + review workflow |
| memory | `services/memory` | MemoryRecord store for S08 |

## 2. Critical path vs parallel streams vs background loops

The split is declared in `ExecutionPlan` *(implemented as a contract; the
executor is scheduled)*:

```python
critical_path:    ["s01", "s02", "s03", "s06", "s11"]   # sequential, each blocks the next
parallel_streams: ["s04", "s05", "s07", "s10"]          # concurrent, advisory directives
background:       ["s08", "s12"]                        # async, never block emission
```

- **Critical path.** A station's output is required before the next station
  runs. S01→S02→S03→S06→S11 form the blocking spine of request processing.
  S03's gate is fail-closed: if the Watcher is unavailable, errors, or is
  degraded, the segment is **withheld** rather than emitted (see §5).
- **Parallel streams.** S04, S05, S07, S10 run concurrently against the same
  immutable `ExecutionContext` snapshot and emit **advisory** directives
  (e.g. "revise", "re-anchor", "cut"). They do not mutate the candidate; the
  orchestrator merges their directives under the reconciliation policy (§4).
- **Background loops.** S08 (memory consolidation) and S12 (final reduction)
  run asynchronously. They must respect `ctx.cancelled` / `ctx.deadline_ms`
  and never block the stream plane.

**Open question (flagged, not resolved).** The contract default omits `s09`
(Parallel Paths) from all three lists, while audit issue #2 describes the
parallel band as "S4–S5, S7–S10" (which would include S09). The intended
placement of S09 is therefore **ambiguous in the supplied materials**: it
cannot be confirmed whether S09 is parallel-advisory or on the critical path.
Do not implement S09 placement until the design brief is clarified.

## 3. Station computational contract *(implemented)*

From `packages/contracts/python/pazuzu_contracts/stations.py`:

- `run(ctx)` receives an **immutable** `ExecutionContext` snapshot
  (`frozen = True`); it must not mutate `ctx`.
- `run(ctx)` returns an **immutable** `StationOutput` (`frozen = True`)
  carrying `data`, `status`, `provenance`, `telemetry`, and `warnings`.
- Error isolation: `timed_run()` catches any exception and converts it to a
  `FAILED` output with the warning `"station raised; isolated by engine"`.
  A station can never crash the engine.
- Expensive work must respect `ctx.cancelled` and `ctx.deadline_ms`.
- `Provenance` records `request_id`, `correlation_id`, `station_id`,
  `station_version`, `input_hash`, `created_at`, `actor`.
- `ExecutionContext.with_output()` / `with_cancelled()` return **new**
  contexts — the pipeline is a dataflow fold over immutable snapshots, not
  sequential state mutation (this answers audit issue #7: the architecture is
  a dataflow graph with a fixed critical-path spine, not an imperative
  pipeline).

## 4. Reconciliation policy

**Precedence (design intent, executor scheduled):**

```
s10  >  s05  >  s04  >  s07
```

When parallel-stream stations return conflicting modification directives for
the same segment/token:

1. The orchestrator collects all directives keyed by target segment.
2. Conflicts are resolved by station precedence: **S10 (Divergence Cut)**
   overrides **S05 (Vector Current)**, which overrides **S04 (Swarm
   Agreement)**, which overrides **S07 (Breath Divider)**.
3. The winning directive is applied; losing directives are preserved in
   telemetry (`reconciliation.losers`) for offline analysis — nothing is
   silently dropped.
4. If two directives come from the *same* station (should not happen for
   pure stations), the later-arriving one wins and the event is logged as a
   contract violation.

This directly addresses audit issues #2 (unspecified merge protocol) and
#65 (S5-drift-correction vs S10-fracture-correction hierarchy): under the
precedence rule, an S10 cut always wins over an S05 re-anchor on the same
segment. **Status: specified, not implemented** — `services/orchestrator`
is an empty directory.

## 5. Immutability of station outputs

- `StationOutput` and `ExecutionContext` are Pydantic models with
  `model_config = {"frozen": True}` *(implemented)*.
- There is no shared mutable request state. Each station sees the outputs of
  its predecessors only through the context snapshot it was handed.
- Corrections are **compensating outputs**, never edits: a station that
  disagrees with an earlier station emits a new `StationOutput` with
  `status=REVISED`/`QUARANTINE` and its own provenance; the earlier output
  remains in the record (audit issue #10's namespace collision is resolved
  by keeping S11's active-transformation records distinct from the
  dead-letter quarantine store in `services/quarantine`).

## 6. Fail-closed S3 gate

The Dual Ward (S03) gate policy *(specified; gate enforcement scheduled)*:

- The gate requires a Watcher verdict. **No verdict ⇒ no emission.**
- Watcher unavailable / timeout / error → the segment is withheld and the
  stream emits a `withheld` SSE event. The system degrades to the failover
  rule (Keeper-role provider assumes both roles) **only** if the deployment
  explicitly enables degraded mode, and degraded output is watermarked
  `ward:degraded` (audit #41: watermarking is spoofable if the response
  schema is public — the watermark is an internal marker, not a security
  control).
- **Known limitation (audit #36):** the Watcher scores asynchronously "one
  segment behind". A fail-closed gate stops *future* emissions; it cannot
  retract a segment already emitted. The gate is fail-closed for the
  not-yet-emitted stream, not retroactive. This is a documented residual
  risk, not a solved problem.
- **Known limitation (audit #43):** failover mode ("Keeper speaks alone")
  contradicts the intersection rule ("only intersection is spoken"). The
  failover path exists for availability; its use is a logged policy
  exception, watermarked, and counted in `pazuzu_s3_degraded_segments`.

## 7. Latency budget *(scheduled)*

Audit issue #5 requires an end-to-end latency budget summation; none exists
yet. The critical-path spine (S01→S02→S03→S06→S11) plus provider generation
time must be budgeted per deployment with per-station SLOs in
`ExecutionPlan.timeouts_ms` (contract field exists; values are deployment
configuration, **scheduled**). Queuing: station worker pools must be bounded
(Little's Law) — pool sizing is a deployment concern, see
`docs/operations/deployment.md`.
