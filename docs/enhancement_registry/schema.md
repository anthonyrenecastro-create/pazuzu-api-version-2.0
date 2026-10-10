# Enhancement Registry — Field Specification

Every enhancement record (`records/EXXX.md`) MUST contain all of the following
fields. Unknown values are marked `tbd` with a reason; values are never invented.

## Required fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Enhancement ID, zero-padded: `E001` … `E096`. |
| `original_spec` | string | Faithful 1–3 sentence paraphrase of the supplied enhancement text. |
| `technical_purpose` | string | What capability, property, or guarantee the enhancement adds to v2.0, in engineering terms. |
| `dependencies` | string[] | IDs of other enhancements and/or audit records (S001…) this depends on. Empty array if none. |
| `affected_modules` | string[] | v2.0 implementation files/modules touched (e.g. `stations/s01_chimera/router.py`). |
| `acceptance_criteria` | string[] | Observable, testable conditions that define "done". |
| `test_coverage` | string[] | Planned test identifiers (e.g. `tests/unit/test_s01.py::test_...`); `"none — scheduled"` if not yet planned. |
| `implementation_status` | enum | One of: `not_started` / `in_progress` / `implemented_unverified` / `resolved_verified` / `blocked` / `deferred`. `resolved_verified` requires a real passing test, named. |
| `cost_perf_implications` | string | Expected cost/latency/memory/complexity impact, with numbers or explicit unknowns. |

## Optional fields

| Field | Type | Description |
|---|---|---|
| `see_also` | string[] | Related audit records or enhancements. |
| `notes` | string | Anything that does not fit above. |

## The 12 technical-area groupings

Each enhancement is filed under exactly one primary technical area. These
groupings are **provisional**: they were derived from the architecture domains
visible in the supplied audit (doctrine/topology, the station pipeline, gateway,
telemetry) because the enhancement source defining the authoritative 12 areas was
not supplied. **Confirm or replace them when E1–E96 arrive.**

| Area ID | Provisional name | Covers |
|---|---|---|
| TA-01 | Doctrine & topology | Pipeline semantics, execution model, merge/reconciliation, versioning |
| TA-02 | S1 Chimera Gate | MoE routing, expert pool, discord detection, stitching |
| TA-03 | S2 Sexagesimal Turn | Context ring, bridge attention, KV-cache tiering, archive |
| TA-04 | S3 Dual Ward | Keeper/Watcher, calibration, failover, retry policy |
| TA-05 | S4 Swarm Agreement | Branching, medoid consensus, replay, completion policy |
| TA-06 | S5 Vector Current | Trajectory analysis, drift detection, re-anchoring |
| TA-07 | S6 Thermodynamic Brake | Sampling control, entropy targeting, anti-windup |
| TA-08 | S7–S12 stations | Stations beyond the supplied audit scope (records pending full audit) |
| TA-09 | Ingestion gateway & API | Auth, mTLS, endpoints, rate limiting, attestations |
| TA-10 | Telemetry & observability | Metrics, digests, dashboards, eval harnesses |
| TA-11 | Security hardening | Threat-model-driven fixes across stations |
| TA-12 | Performance & capacity | Latency budgets, memory sizing, throughput |

## Record template

```markdown
# EXXX — <short title>

- **ID:** EXXX
- **Technical area:** TA-NN (<name>)
- **Original spec:** ...
- **Technical purpose:** ...
- **Dependencies:** ...
- **Affected modules:** ...
- **Acceptance criteria:** ...
- **Test coverage:** ...
- **Implementation status:** not_started
- **Cost/perf implications:** ...
```
