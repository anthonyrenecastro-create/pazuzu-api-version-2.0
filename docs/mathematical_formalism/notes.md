# PAZUZU-API v2.0 — Mathematical Formalism: Honesty Notes

**Purpose.** Classify every piece of math the system depends on as
**rigorous**, **heuristic**, or **removed for invalidity** — so nobody
mistakes a metaphor for a measurement. Status: notes only; the formalism
registry (`vm/formalism_registry`, with `FormalismEntry.verification_status`
values `IMPLEMENTED_TESTED | IMPLEMENTED_UNVERIFIED | REVIEW_REQUIRED |
NOT_IMPLEMENTED`) is **scheduled**.

## 1. Rigorous (well-defined, computable, correctly applied)

- **Reconciliation precedence (s10 > s05 > s04 > s07).** Not mathematics in
  the analytic sense — a deterministic total order over conflicting
  directives. Rigorous because it is unambiguous, terminating, and
  auditable: given the same directive set, the merge result is identical.
  (Specified; executor scheduled.)
- **PD temperature control (S06).** `T_{t+1} = T_t · exp[−κ_e(H_t − H*) −
  κ_d·Ḣ_t]` is a legitimate discrete-time proportional-derivative
  controller on the scalar signal H_t. The *control theory* is sound; the
  *application* has the caveats in §3 (static setpoint, noisy derivative).
  Rigorous as a controller, misapplied as a semantic governor (audit #77:
  it governs the sampling distribution only).
- **Finite-difference divergence (S05).** ∇·v approximated by finite
  differences over consecutive segment embeddings is mathematically
  well-defined. It is *noisy* (see §2), but it is not *wrong* the way the
  curl was.
- **Immutable fold semantics.** The pipeline-as-dataflow-fold over frozen
  contexts (`with_output`/`with_cancelled`) is a well-defined functional
  construction; error isolation via `timed_run` is total (every exception
  maps to a `FAILED` output).
- **t-digest / EVT p99 telemetry.** Standard, well-defined streaming
  quantile machinery — but audit #8 notes no merge schema exists for
  distributed replicas yet. Rigorous math, missing systems work.

## 2. Heuristic (computable, but not what the name promises)

- **S03's four axes.** Scores in [0,1] from LLM judges with **no calibration
  procedure** (audit #35). They are heuristics with unknown error bars, not
  calibrated measurements. The `min(axes) ≥ 0.75` conjunction (audit #38)
  compounds this: strict logic over uncalibrated inputs.
- **S05's drift proxies.** Finite-difference divergence in high-D embedding
  space is dominated by noise (audit #57); using it as a "semantic drift"
  signal is a heuristic with an unmeasured false-positive rate. The
  re-anchoring response (inject top-3 archive blocks, audit #59) is a
  heuristic policy, not a derived optimum.
- **S04's medoid-as-truth.** Selecting the medoid of 3–5 continuations
  assumes consensus ≈ correctness (audit #51) — false in adversarial
  domains. A useful heuristic for fluency, not a truth procedure.
- **S02's retention model.** R(k) = exp(−k/60·λ) assumes memoryless
  exponential decay (audit #27); real forgetting is power-law. The formula
  is computable and simple — and wrong in functional form.
- **S01's disagreement metric.** D = 1 − cos(h_i, h_j) on unaligned hidden
  states (audit #13) is a heuristic proxy for contradiction with known
  failure modes.

## 3. Removed for invalidity

- **3D curl on embeddings (S05) — REMOVED, audit #58.** |∇×v| via pairwise
  cross products of consecutive displacements is *undefined* for embeddings
  of dimension d ≫ 3: the cross product does not exist outside 3D
  (and 7D), and embedding spaces are orientation-ambiguous under sign flips
  (audit #61). This was a **fatal mathematical error** in the v1 formalism.
  It has been struck from the S05 specification. Any code, doc, or diagram
  referencing embedding-space curl is stale and must be updated.
  - *Boundary of the removal:* curl remains legitimate **only** where a 3D
    embedding is explicitly constructed (cf. `vm_notes.md` §IV item 38:
    "in 3D graph-embedding only; flag if generalized"). No such construction
    exists in the pipeline, so no curl exists in the pipeline.

## 4. Stipulated constants (VM layer — not physics)

From `_source/vm_notes.md`, recorded here so they are never misread:

- `hbar_thaum ≈ 1.05e-7 J·s`, `E_ref ≈ 1e-12 J/op`, `Lambda_0 ≈ 1e-3 J/m⁴`
  are **stipulated parameters**, not measured physical constants.
- "Thaumic uncertainty" ΔxΔp ≥ hbar_thaum/2 is an **analogy**, not quantum
  mechanics. "Teleportation", "mana exchanges", "quantum" ops are named
  abstract operations with documented semantics, not physical claims.
- Dimensionally inconsistent equations → registry status
  `REVIEW_REQUIRED`, no implementation. (Honesty rule from the VM notes.)

## 5. Open formal questions

1. ROC operating points for the S03 gate (audit #3): without specified
   false-accept/false-reject points, "threshold, not wall" is a metaphor.
2. Controller stability margins for S06 (audit #73): gain/phase margin
   telemetry required before production.
3. Calibration protocol for S03 axes (audit #35, #44): needs human-label
   ground truth in the telemetry pipeline.
