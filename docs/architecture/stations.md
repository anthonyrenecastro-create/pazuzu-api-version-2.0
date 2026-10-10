# PAZUZU-API v2.0 — Station Reference (S01–S12)

**Status note (read first).** The station *interface* (`Station` ABC,
`StationManifest`, `StationOutput`, `ExecutionContext`) is **implemented** in
`packages/contracts/python/pazuzu_contracts/stations.py`. **No station logic
is implemented**: all twelve `stations/sXX_*` directories are empty
(2026-10-09). The sections below describe the *specified* purpose,
computational contract, and algorithms for each station, plus **known
limitations** drawn from the supplied audit issues #1–#78 (which cover S01–S06
only; issues #79–#144 were not supplied, so S07–S12 limitations are flagged
from design review, not from audit evidence).

Legend: **[A#n]** = supplied audit issue number. **[D]** = design-intent
statement from the brief, not yet audited or implemented.

---

## S01 — Chimera Gate

**Purpose.** MoE-style routing gate: decompose the incoming request, route
sub-queries to provider experts, detect inter-expert disagreement, and stitch
a single candidate with provenance tags.

**Computational contract.** Input: `ctx.prompt` + parameters. Output:
`data = {routed_experts, discord_score, sub_queries, stitched_candidate,
provenance_tags}`. Pure function of the context snapshot; may call provider
adapters only through `services/providers`.

**Key algorithms (specified).**
- Gating network G(x) = softmax(Wx); top-2 experts active.
- Pairwise disagreement D = 1 − cos(h_i, h_j) on expert hidden states.
- On high discord: decompose into sub-queries, re-route, stitch with
  provenance tags.

**Known limitations.**
- [A#11] G(x) = softmax(Wx) is a dense linear map; production MoE routers use
  **noisy top-k gating with load-balancing loss**. The spec's router is
  outdated and risks routing collapse (no per-expert utilization telemetry is
  specified — [A#16]).
- [A#13] D = 1 − cos(h_i, h_j) on hidden states is a poor proxy for semantic
  contradiction: orthogonal vectors can mean the same thing in unaligned
  representation spaces.
- [A#17] The "stitch with provenance tags" algorithm is **undefined**
  (concatenation? attention-overlap? LLM summary?). Unimplementable as
  specified.
- [A#14] Recursive decomposition on high discord has no termination proof;
  sub-queries can re-trigger discord → **bounded recursion is required**
  (max depth + deadline enforcement), currently unspecified.
- [A#19] Computing routing uncertainty over all expert hidden states is
  synchronous and dense, contradicting the sparse-activation performance
  claim.
- [A#21] "Silent Steward" is a misnomer: the station decomposes and stitches,
  i.e. it is verbose, not silent.

---

## S02 — Sexagesimal Turn

**Purpose.** Context management: a ring buffer of 60 macro-blocks (≤512
tokens each) with bridge attention, rolling summarization of evicted blocks,
and KV-cache tiering.

**Computational contract.** Input: conversation history + `ctx`. Output:
`data = {active_blocks, evicted_summaries, bridge_salience, retention_probe}`.
Must be side-effect-free w.r.t. the context; archive writes go through
`services/memory`.

**Key algorithms (specified).**
- 60-block ring, sparse bridge attention every 6th block.
- Rolling deep-archive summarization of the oldest blocks.
- Retention model R(k) = exp(−k/60 · λ); KV-cache tiering hot/warm/cold.

**Known limitations.**
- [A#23] 60 × 512 caps managed context at **30,720 tokens** — far below
  modern 128k+ agentic/RAG loops. This is a hard architectural ceiling, not a
  tuning parameter.
- [A#27] R(k) assumes **exponential (memoryless) decay**; human and LLM
  context forgetting is better modeled as **power-law (recency effect)**.
- [A#30] The rotation counter k's unit is undefined (per request? per
  token?). Per-request rotation would rotate mid-sentence in multi-turn
  chats.
- [A#31] Ring vs cylinder topology is undecided: does block 1 attend to
  block 60 (closure), or is the structure a cylinder with birth/death ends?
- [A#32] The "6° bridge" (360/60) is geometric numerology; attention heads do
  not map to degrees.
- [A#33] Summarizing evicted blocks needs an auxiliary model call — a
  **latency spike on the critical path** during context shifts.
- [A#34] No mechanism for the user to **pin** a macro-block (e.g. system
  prompt) against rotation/summarization. `MemoryRecord.pinned` exists in
  the memory contract but is not wired to S02.

---

## S03 — Dual Ward

**Purpose.** Keeper/Watcher safety gate: the Keeper (primary provider)
generates a segment; the Watcher (independent provider/judge) scores it on
4 axes in [0,1]; only the intersection is spoken. Fail-closed gate (see
`overview.md` §6).

**Computational contract.** Input: candidate segment. Output:
`data = {axis_scores[4], decision: approve|revise|reject|quarantine,
regenerations}`. Must emit a decision for every segment; no silent passes.

**Key algorithms (specified).**
- 4-axis scoring, gate rule `min(axes) ≥ 0.75`.
- One regeneration with tightened temperature on reject.
- DeepSeek-R1 reasoning mode on low Keeper confidence.
- Failover: provider outage → alternate provider assumes both roles,
  output watermarked `ward:degraded`.

**Known limitations.**
- [A#35] **The 4 axes are heuristics, not calibrated judges.** LLM judges are
  systematically miscalibrated (overconfident); no calibration procedure
  (e.g. Platt scaling, human-label validation) is specified. Treat all axis
  scores as uncalibrated until a calibration protocol exists.
- [A#38] `min(axes) ≥ 0.75` is a strict conjunction: one axis at 0.74 with
  the rest at 1.0 fails. A weighted combination or Pareto rule would be more
  robust; the conjunction was chosen for auditability, at the cost of false
  rejects.
- [A#37] The Keeper (Grok) generates the confidence score that triggers the
  Watcher's deep-reasoning mode — a compromised Keeper reports high
  confidence and bypasses scrutiny. **Self-reported confidence must not gate
  oversight.**
- [A#36] Watcher runs one segment behind; kill-switch cannot unsay emitted
  tokens (documented in `overview.md` §6 as residual risk).
- [A#40] Failover to DeepSeek-V3/R1 will violate p99 latency SLOs (R1
  chain-of-thought vs the 250 ms Watcher budget in [A#45]).
- [A#44] `pazuzu_s3_false_reject_rate` is uncomputable without ground-truth
  human override labels, which are not in the telemetry pipeline.
- [A#43] Failover ("Keeper speaks alone") contradicts the intersection rule
  — logged as a policy exception, not a resolution of the contradiction.

---

## S04 — Swarm Agreement

**Purpose.** Generate 3–5 speculative continuations, select the medoid, and
emit a consensus directive (parallel stream, advisory).

**Computational contract.** Input: context snapshot. Output:
`data = {branches, medoid_index, cluster_dispersion, directive}`.
Advisory only — the orchestrator may override per reconciliation precedence
(S04 loses to S10 and S05).

**Key algorithms (specified).**
- Fan-out of 3–5 continuations with distinct seeds; pairwise embedding
  distances; medoid selection; tie-break by Watcher score; early-exit on
  consensus.

**Known limitations.**
- [A#47] Medoid computation is **O(N²)** in pairwise distances over
  high-dimensional embeddings.
- [A#48] Speculative branches need duplicate KV caches: **3–5× memory
  overhead**, unaccounted in deployment sizing.
- [A#52] The spec claims both "wait-for-all" and "early-exit" — these
  contradict. Early exit is non-deterministic (fastest branch wins, not
  best).
- [A#51] Consensus ≠ truth: in adversarial domains (math puzzles, trick
  questions) the correct answer is often the outlier. Medoid selection has an
  anti-novelty bias.
- [A#55] Replay determinism requires bit-identical floating point across
  nodes; **GPU non-determinism makes cross-node exact replay impossible**.
  Replay is approximate — document tolerance, don't promise determinism.
- [A#50] Publishing seed + routing record on the replay endpoint lets
  attackers binary-search expert activation boundaries. Replay records must
  be access-controlled.
- [A#49] Tie-break by Watcher score couples S04 to S03, violating the
  stated parallelism. Under the reconciliation policy this is a
  *read* of S03's output, not a control dependency — acceptable, but it must
  not block on S03's verdict.

---

## S05 — Vector Current

**Purpose.** Track the embedding trajectory of emitted segments; detect
semantic drift via finite-difference divergence; issue re-anchor directives
by injecting archive blocks (parallel stream, advisory; loses to S10).

**Computational contract.** Input: segment embeddings + S02 archive refs.
Output: `data = {divergence, drift_flag, injected_blocks, directive}`.

**Key algorithms (specified).**
- Finite-difference divergence ∇·v over consecutive segment embeddings.
- High-divergence → inject top-3 archive blocks as re-anchoring context.

**Known limitations.**
- [A#58] **The 3D curl |∇×v| was REMOVED for invalidity.** The cross product
  is undefined for embeddings of dimension d ≫ 3; orientation in embedding
  space is ambiguous under sign flips ([A#61]). There is no curl in S05.
  See `docs/mathematical_formalism/notes.md`.
- [A#57] Finite-difference divergence in high-D space is **extremely noisy**
  (curse of dimensionality). It is a heuristic drift *proxy*, not a
  measurement of "semantic divergence" in any rigorous sense.
- [A#63] Divergence is computed on embeddings of **already-emitted** tokens:
  correction is post-hoc, not preventive, despite the "ruin prevented before
  it takes flight" framing.
- [A#59] Re-anchoring on drift is a heuristic that can fight legitimate
  user pivots (e.g. deliberate topic change). No intent-vs-drift
  discriminator is specified.
- [A#60] Embedding every emitted segment on the critical path costs
  ~5–10 ms/token of embedding-model forward pass — a streaming throughput
  risk that must be budgeted.
- [A#64] **Embedding trajectories must never be exposed to API clients.**
  They leak internal semantic geometry and aid adversarial prompt
  optimization. Per the threat model, raw trajectory data is internal-only
  (see `docs/threat_model.md` and audit #66: `GET /v1/field` admin-only).
- [A#62] Live quiver-plot dashboards require t-SNE/UMAP reduction computed
  live — computationally prohibitive; dashboards must use sampled/offline
  projections.

---

## S06 — Thermodynamic Brake

**Purpose.** Entropy governor on the sampling distribution: PD controller
adjusting temperature from output-token entropy (critical path).

**Computational contract.** Input: token distribution statistics.
Output: `data = {temperature, top_p, entropy, controller_state}`. Adjusts
sampling parameters only — it does not touch model weights or context
([A#77]).

**Key algorithms (specified).**
- PD update: `T_{t+1} = T_t · exp[−κ_e(H_t − H*) − κ_d·Ḣ_t]`
  with anti-windup clipping and nucleus top-p tightening.

**Known limitations.**
- [A#69] The derivative term Ḣ_t on discrete entropy is highly volatile and
  will cause temperature oscillation ("hunting") without derivative
  filtering (e.g. low-pass on Ḣ_t) — unspecified.
- [A#70] Low entropy ≠ mode collapse: deterministic prompts ("What is
  2+2?") legitimately have low entropy; the controller would inflate
  temperature on factual queries. **H* must be context-dependent** ([A#75]:
  static H* is wrong for both brainstorming and coding).
- [A#71] Temperature scaling and top-p truncation interact non-linearly;
  their joint effect is uncalibrated.
- [A#72] Post-hoc anti-windup clipping is incomplete; true anti-windup needs
  back-calculation of the integral term (here: of the accumulated
  proportional correction).
- [A#73] No telemetry for controller stability (gain/phase margin) —
  required before the loop can be trusted in production.
- [A#76] An attacker can craft prompts that drive the controller into a
  high-entropy loop to exhaust token budgets. Rate/entropy caps per request
  are required (see threat model, DoS).
- [A#74] Fixed sliding window for entropy; optimal window length is
  context-dependent (long creative vs short factual generations).

---

## S07 — Breath Divider [D]

**Purpose (design intent).** Segment the token stream into scored segments
("breaths") that S03's Watcher can judge asynchronously. Pacing/segmentation
policy: sentence/clause boundaries, max segment length, urgency fast-path.

**Computational contract (specified, unimplemented).** Input: token stream.
Output: `data = {segments, boundaries, pacing_policy}`. Advisory (parallel
stream; loses reconciliation to S04, S05, S10).

**Key algorithms (specified).** Boundary detection heuristics
(punctuation/clause structure, length caps); urgency override for
safety-critical content.

**Known limitations.**
- Audit issues #79–#144 were **not supplied**; S07 has no audit coverage in
  the materials. The following are design-review flags, not audit findings:
- Segmentation boundaries are **heuristics**, not semantic units — a safety
  judgment scoped to a heuristic segment can split a harmful construction
  across two "safe" halves.
- S07's segmentation interacts with S03's one-segment-behind lag: segment
  sizing directly sets the exposure window of already-emitted tokens.
- No backpressure protocol is specified between the divider and the stream
  plane if segmentation falls behind generation.

---

## S08 — Living Memory [D]

**Purpose (design intent).** Long-term memory: consolidate interaction
history into `MemoryRecord`s (event/fact/telemetry/evaluation), serve
retrieval for S02 re-anchoring and S05 drift correction. Background loop.

**Computational contract (specified, unimplemented).** Input: execution
records, telemetry. Output: `data = {stored_records, retrieval_hits}` via
`services/memory`. Uses `MemoryRecord` (with `pinned`, `expires_at`,
`version`) and `embedding_ref` pointers — embeddings stored by reference,
not inline.

**Key algorithms (specified).** Consolidation pipeline (dedupe, fact
extraction, expiry); vector retrieval over `embedding_ref`s; pin/expiry
policy.

**Known limitations.**
- **S08 has no LoRA and no fine-tuning of any kind.** "Living" memory is
  retrieval-only: it stores records and retrieves them into context. There
  is no parameter adaptation, no adapter training, no continual learning in
  the weights. Any documentation or marketing implying the model "learns"
  from the user must be corrected — the mechanism is retrieval-augmented
  context, not learning.
- Consolidation runs in the background and is **eventually consistent**:
  a fact stored mid-conversation is not guaranteed visible to S02/S05 in
  the same request.
- `MemoryRecord.pinned` exists in the contract but the pinning UX/API
  (cf. [A#34]) is unspecified.

---

## S09 — Parallel Paths [D]

**Purpose (design intent).** Maintain alternate continuation branches across
decision points (distinct from S04's single-step swarm: S09 tracks
multi-step path alternatives for backtracking).

**Computational contract (specified, unimplemented).** Input: decision
points + branch states. Output: `data = {paths, active_path,
backtrack_points}`.

**Key algorithms (specified).** Branch bookkeeping with pruning by
Watcher score and divergence thresholds.

**Known limitations.**
- **Placement ambiguous**: omitted from the `ExecutionPlan` contract
  defaults while audit #2 describes S7–S10 as the parallel band (see
  `overview.md` §2). Do not place S09 until clarified.
- Multi-step branch state multiplies memory cost on top of S04's already
  3–5× KV-cache overhead ([A#48] applies a fortiori).
- No pruning policy is specified; unbounded path retention is a memory leak
  by design.

---

## S10 — Divergence Cut

**Purpose.** Hard cut on fractured trajectories: when a segment is judged
irreparably off-course, emit a cut directive that terminates the branch and
forces restart/re-route. **Highest precedence** in reconciliation
(s10 > s05 > s04 > s07).

**Computational contract (specified, unimplemented).** Input: segment +
parallel-stream directives. Output: `data = {cut: bool, cut_reason,
restart_directive}`. A cut is terminal for the branch; it is recorded with
full provenance.

**Key algorithms (specified).** Fracture detection (threshold on
S05-style drift proxies + Watcher reject); cut vs revise decision rule.

**Known limitations.**
- Audit issues #79–#144 were **not supplied**; no direct audit coverage.
  Design-review flags:
- The cut/revise boundary is the highest-stakes decision in the pipeline
  and its criteria are unspecified — a hair-trigger S10 destroys valid
  generations; a lax S10 makes its precedence meaningless.
- Precedence over S05 ([A#65] resolved by the s10 > s05 rule) means an S10
  cut discards S05's re-anchor work; the wasted compute must be visible in
  telemetry (`reconciliation.losers`).

---

## S11 — Pattern Quarantine

**Purpose.** Active transformation station on the critical path: sanitize or
isolate flagged content. Distinct from the quarantine *store*
(`services/quarantine`): S11 transforms, the service stores and workflows
the review (this resolves audit #10's namespace collision).

**Computational contract (specified, unimplemented).** Input: flagged
segment + reason codes. Output: `data = {action:
sanitize|isolate|escalate, transformed_segment, quarantine_ref}`. Emits a
`QuarantineRecord` (status `quarantined`) for anything isolated.

**Key algorithms (specified).** Pattern matching against quarantine
rulesets; sanitization transforms; escalation to human review.

**Known limitations.**
- Audit issues #79–#144 were **not supplied**; no direct audit coverage.
  Design-review flags:
- The quarantine ruleset format, versioning, and update cadence are
  unspecified — a stale ruleset is a silent safety regression.
- Sanitization transforms must be proven non-lossy for benign content;
  no such property is specified.
- S11 is on the critical path: a slow ruleset engine blocks emission.
  Budget it in the latency plan.

---

## S12 — Bronze Reduction

**Purpose (design intent).** Final reduction: collapse the surviving
candidates/directives into the single emitted output; attach final
provenance and telemetry. Background loop in the contract default (runs
post-emission bookkeeping), though its reduction decision logically gates
emission — placement tension noted below.

**Computational contract (specified, unimplemented).** Input: all station
outputs for the request. Output: `data = {final_text, reduction_trace,
provenance_chain}`.

**Key algorithms (specified).** Reduction over candidate set per the
reconciled directives; provenance chain assembly.

**Known limitations.**
- The contract default lists S12 as **background**, but a "final reduction"
  that selects the emitted text is logically on the emission path. This
  tension is unresolved in the supplied materials — clarify whether S12's
  reduction gates emission or only records it.
- Reduction-trace completeness is what makes the pipeline auditable;
  an incomplete trace silently breaks repudiation guarantees (see threat
  model).
