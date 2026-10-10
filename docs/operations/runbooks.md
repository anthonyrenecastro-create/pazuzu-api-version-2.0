# PAZUZU-API v2.0 — Operational Runbooks

**Status: procedures specified, system not built.** These runbooks describe
intended operator actions. Step numbers referencing endpoints/config that
don't exist yet are marked *(scheduled)*. Do not treat these as tested
procedures.

## RB-1 — Provider outage / failover

**Trigger:** `pazuzu_provider_error_rate{provider}` alert, or `/v2/ready`
failing on provider init.

1. Confirm scope: which provider, which models, error class (auth vs
   upstream 5xx vs timeout). Check `services/providers` logs
   *(scheduled)*.
2. **Failover policy (specified):** the orchestrator's `ExecutionPlan`
   `fallbacks` map names the standby provider per role. If the Keeper-role
   provider (default: Grok-class) is down, the Watcher-role provider
   (default: DeepSeek-class) **assumes both roles**.
3. **SLO warning:** the dual-role failover is known to violate p99 latency
   SLOs (audit #40 — R1 chain-of-thought vs the 250 ms Watcher budget).
   Expect elevated `pazuzu_s3_watcher_timeout_total` and degraded-mode
   entries during failover. This is accepted; do not "fix" it by widening
   the Watcher budget without recalibrating the gate thresholds.
4. All output produced during dual-role operation is watermarked
   `ward:degraded` and counted in `pazuzu_s3_degraded_segments`. The
   watermark is an internal marker, not a security boundary (audit #41).
5. **Known contradiction (audit #43):** dual-role operation means "Keeper
   speaks alone", violating the intersection rule. Every failover entry is
   therefore a logged policy exception in the audit log — review the
   exception count before failing back.
6. Failback: when the primary recovers, drain dual-role traffic, verify
   `/v2/ready`, then restore the primary in the `fallbacks` map. Keep the
   degraded window's telemetry cohort separate (different effective
   `station_version` behavior — see `architecture/pipeline-versioning.md`).

## RB-2 — Watcher unavailable (fail-closed / degraded)

**Trigger:** S03 Watcher timeouts/errors; `pazuzu_s3_gate_withheld_total`
spiking.

1. **Default policy is fail-closed:** if `PAZUZU_S3_DEGRADED_MODE=off`
   (default), segments without a Watcher verdict are **withheld** — the
   stream emits `withheld` SSE events, not text. Do not override this to
   restore availability without written sign-off; availability is not a
   safety argument.
2. If degraded mode is explicitly enabled (`watermarked`), the Keeper-role
   provider assumes both roles per RB-1 steps 3–5. Output is watermarked
   `ward:degraded`.
3. **Residual risk (audit #36):** segments emitted *before* the Watcher
   failure cannot be retracted. Identify the exposure window from the
   stream log (`withheld` events mark where the gate engaged) and assess
   whether already-emitted segments need quarantine review (RB-3).
4. Recovery: restore the Watcher provider, confirm verdicts flowing
   (`pazuzu_s3_verdicts_total` increasing), then close the incident. The
   withheld segments are **not** retroactively emitted — clients must
   re-request.

## RB-3 — Quarantine review procedure

**Trigger:** `QuarantineRecord` created (S11 isolate/escalate, or manual).

1. List: `GET /v2/quarantine?status=quarantined` *(scheduled)*. Triage by
   `risk_class` (critical → high → medium → low).
2. Check out one record for review (Redis lock ensures single reviewer):
   `POST /v2/quarantine/{id}/review` → status `under_review`,
   `reviewed_by` set to your principal *(scheduled)*.
3. Inspect `payload_ref`, `reason_code`, `station_id`, and the S11
   `transformed_segment`. Decide:
   - **Release** (`released`): content is benign; record the rationale in
     `history`. The isolated payload is *not* re-injected into the
     original stream — release only clears the hold for downstream use.
   - **Destroy** (`destroyed`): content is harmful; payload purged, rationale
     recorded.
   - **Keep quarantined**: needs more evidence; add a `history` note and
     release the lock.
4. Every transition appends to `history` with `reviewed_by` and timestamp.
   Transitions are append-only; there is no "un-review".
5. **SLA (specified):** critical → 1h, high → 4h, medium → 24h, low → 72h.
   Breaches page the on-call.

## RB-4 — Replay procedure

**Purpose:** reproduce a past execution for debugging or audit.

1. `POST /v2/replay` with `{request_id, seed}` *(scheduled)*. The verifier
   service re-runs the recorded `ExecutionPlan` version against the stored
   inputs.
2. **Determinism caveat (audit #55):** exact bit-identical replay across
   different GPU nodes is **impossible** (GPU floating-point
   non-determinism). Replay is *approximate*: the verifier compares
   decisions and directives, not token bytes, and reports a divergence
   summary. Same-hardware, same-seed replays are expected to match
   closely; cross-hardware replays are best-effort.
3. **Access control (audit #50):** replay responses include seed and routing
   records, which can be used to reverse-engineer expert activation
   boundaries. Replay is **admin-scoped**; never expose it to untrusted
   principals.
4. Record the replay verdict (`match | divergent | inconclusive`) in the
   audit log with the original `request_id`.
