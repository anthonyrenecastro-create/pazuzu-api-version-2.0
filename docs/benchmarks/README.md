# PAZUZU-API v2.0 — Benchmark Protocol

**Status: NOT YET RUN. No benchmark numbers exist.** `tests/benchmarks/` is
empty (2026-10-09). This document specifies *what to measure* so that when
benchmarks run, they measure the right things. **There are no results below,
and none are implied.** Any number attributed to PAZUZU-API v2.0 found
elsewhere is invented unless it cites a dated run of this protocol.

## 1. Protocol principles

1. Every benchmark runs against a pinned `(plan_version, station_id,
   station_version)` cohort (see `docs/architecture/pipeline-versioning.md`
   §3). Numbers without a cohort tag are not comparable.
2. Report distributions, not point estimates: p50/p99, and t-digest merges
   across replicas (audit #8's merge schema must exist first).
3. Adversarial and nominal workloads are reported separately; never average
   them into one headline number.
4. Replay-based benchmarks inherit the approximate-determinism caveat
   (audit #55; runbook RB-4).

## 2. What to measure (per prompt §X scope)

### End-to-end (audit #5)
- **Latency budget summation**: per-station `duration_ms` p50/p99 on the
  critical path (S01→S02→S03→S06→S11) + provider generation time, for
  fixed prompt sizes (128 / 1k / 8k input tokens). Verifies the pipeline
  against its SLO instead of asserting one.
- **Cost per request**: Σ `Telemetry.cost_usd` across stations + provider
  spend, same prompt sizes.

### S01 — Chimera Gate (audits #11, #16)
- Routing entropy (`pazuzu_s1_gate_entropy`) **and** per-expert utilization
  rate over a mixed workload — detects routing collapse, which entropy
  alone cannot.

### S02 — Sexagesimal Turn (audits #23, #28)
- **Retention**: needle-in-haystack recall at 8k/16k/30k tokens (the 30,720
  hard cap from audit #23 bounds the test grid); online probing with
  injected synthetic facts for live retention metrics.

### S03 — Dual Ward (audits #3, #35, #44)
- **ROC analysis** of the gate: false-accept / false-reject operating
  points on a human-labeled adversarial + benign corpus. This is the
  measurement that turns "threshold, not wall" from metaphor into design
  (audit #3).
- **Calibration**: judge score vs human-label agreement per axis (audit
  #35); false-reject rate requires the human-override labels from audit
  #44 — the telemetry pipeline must carry them first.

### S04 — Swarm Agreement (audits #47, #53)
- Medoid-selection latency vs branch count (validates the O(N²) concern);
  cluster dispersion distribution; which clusters lost (needed for offline
  S1 re-weighting, audit #53).

### S05 — Vector Current (audits #57, #63)
- Divergence-threshold precision/recall against human-labeled drift events;
  false-positive rate of re-anchor injections (audit #59's
  intent-vs-drift confusion).

### S06 — Thermodynamic Brake (audits #69, #73)
- **Controller stability**: gain/phase margin of the PD loop; temperature
  oscillation ("hunting") incidence on factual vs creative prompts;
  entropy-target tracking error with context-dependent H*.

### Safety / robustness
- **Fail-closed verification**: with the Watcher killed, confirm 100% of
  segments are withheld (never emitted) — the S3 gate's core guarantee.
- **Degraded-mode watermark presence**: `ward:degraded` on all dual-role
  output.
- **DoS resistance**: behavior under rate-limit saturation; S06
  high-entropy-loop attack prompts (audit #76) stay within token caps.

## 3. Acceptance criteria for "benchmarked"

A station is "benchmarked" when: the protocol above ran on a pinned cohort,
distributions (not points) are recorded, the run is reproducible from the
stored `(request_id, seed, plan_version)` records, and known limitations
(e.g. approximate replay) are noted alongside the numbers. Until then, the
station is **unbenchmarked** — which is the status of all twelve.
