# PAZUZU-API v2.0 — Pipeline Versioning

Answers audit issue #9 ("no versioning strategy for the pipeline itself").
**Status:** the tagging *contracts* are implemented; the storage, query, and
migration tooling are **scheduled** (`services/telemetry`, `migrations/`
are empty).

## 1. Two version axes

| Axis | Field | Defined in | Status |
|---|---|---|---|
| **Plan version** | `ExecutionPlan.version`, `ExecutionContext.plan_version` | `models.py` | implemented (contract) |
| **Station version** | `StationManifest.version`, `StationOutput.station_version`, `Provenance.station_version` | `stations.py`, `models.py` | implemented (contract) |

- The **plan version** identifies the orchestration recipe: critical-path
  membership, parallel-stream set, background set, per-station timeouts, and
  fallbacks. Bumping the plan version is required for any change to station
  membership or ordering.
- The **station version** is a semver string owned by each station's
  `StationManifest`. Bumping rules (specified, unenforced):
  - **major**: behavior change visible to downstream stations or clients
    (e.g. S05 dropping curl — had it shipped, that would have been major);
  - **minor**: new telemetry fields, new advisory directives, performance
    changes with identical decisions;
  - **patch**: bug fixes with no behavioral delta.

## 2. Telemetry tagging

Every `StationOutput` carries, immutably:

- `station_id` + `station_version` (who ran),
- `Provenance.input_hash` — sha256 (truncated to 16 hex chars) of
  `{prompt, parameters, plan_version}` (what it ran on),
- `Provenance.request_id` / `correlation_id` (which request),
- `Provenance.created_at`, `actor`.

`ExecutionContext.plan_version` propagates the plan version into every
station's input hash, so a plan change automatically changes the input
hashes of all downstream telemetry — **plan changes are self-tagging**.

## 3. Retroactive distinction (the audit #9 requirement)

"If S5 logic changes, how is retroactive telemetry distinguished?"

By the compound key **(plan_version, station_id, station_version)**:

1. Telemetry rows are immutable and append-only; no row is ever rewritten.
2. Offline analysis groups by the compound key. A query like "S05
   divergence false-positive rate" must filter to a single
   `(plan_version, station_version)` cohort; cross-cohort comparisons are
   explicit and labeled.
3. `Provenance.input_hash` lets analysts detect when identical inputs
   produced different outputs across station versions (behavioral diff).
4. The formalism registry (`vm/formalism_registry`, **scheduled**) records
   which equation/algorithm each `(station_id, station_version)` implements,
   so a behavioral diff can be traced to the exact formalism change.

**Gap:** the telemetry store schema, retention policy, and the cohort-query
tooling are not built yet (`services/telemetry` empty). The tagging
contracts exist; the query path does not. Until it does, retroactive
distinction is possible *in principle* from exported `StationOutput` JSON
but not *in practice* from any running system.

## 4. Migration policy (specified, scheduled)

- Plan versions are append-only: old plans are never edited, only
  superseded. `migrations/` will hold plan-migration scripts, not
  in-place edits.
- Station major bumps require a dual-run (shadow) period: the new version
  runs in parallel streams while the old version remains on the critical
  path, until the behavioral diff is reviewed. (Specified; shadow-runner
  tooling scheduled.)
