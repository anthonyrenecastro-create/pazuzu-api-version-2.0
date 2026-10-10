# Audit Resolution Registry — PAZUZU-API v2.0

## What this is
This registry tracks the disposition of every issue raised in the **PAZUZU-API v1.0
Technical Review Report** and how v2.0 addresses it. Each issue gets one record
file in `records/` (S001.md … S078.md); `index.json` is the machine-readable index.

## Source coverage
- **Registered:** issues **#1–#78**, the complete supplied portion of the audit.
- **NOT registered:** issues **#79–#144** — the supplied source was truncated mid-S6
  at issue #78. They do not exist in this registry and were not invented.
- **NOT registered:** enhancements **E1–E96** — none were supplied. See
  `../enhancement_registry/`.

## Record fields
Each record contains: Audit ID, Title, Classification, Severity (+ rationale),
Original defect description, Affected subsystem, Root cause, Proposed correction,
Implementation files, Verification method, Test identifier, Status, Status
justification, Residual risk.

## Statuses
| Status | Meaning |
|---|---|
| `resolved_verified` | Fix implemented AND a real, passing test exists (named in the record). |
| `implemented_unverified` | Correction designed into v2.0 modules, but no implementation/test has run yet. |
| `partially_resolved` | Part of the correction is in place; remainder outstanding. |
| `scheduled` | Correction planned (often doc-only or blocked on data/measurements); not started. |
| `blocked` | Cannot proceed until an external dependency resolves (dependency named). |
| `not_applicable` | Issue does not apply to v2.0 (e.g., decorative mythology naming with no behavioral claim). |

**Honesty rules applied:** Nothing is marked `resolved_verified` unless a real test
exists — none do yet, so no record carries it. No issue was closed by explanation
alone. `[HST]` mythology-mismatch issues received doc/terminology corrections with
`scheduled` or `not_applicable` status.

## The fatal-designation gap
The supplied source references **"eight fatal defects"** but never enumerates which
of the 144 issues they are. Consequently **no record is marked fatal**; severity was
assigned by engineering judgment (high/medium/low) with a rationale in each record.
See `GAP_ANALYSIS.md` for what must happen when the full audit arrives.
