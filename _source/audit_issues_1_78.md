# PAZUZU-API v1.0 — Technical Review Report (SUPPLIED PORTION)
# Transcribed from source materials 2026-10-09. Issues #1–#78 were supplied.
# Issues #79–#144 were NOT supplied (source truncated mid-S6 at issue #78).
# No E1–E96 enhancements were supplied. Do NOT invent them.

## Bug Classification
[ARC] architectural flaw · [ALG] algorithmic error · [MTH] mathematical misuse · [SEC] security gap · [PERF] performance bottleneck · [API] interface defect · [OBS] observability gap · [HX] UX/dashboard issue · [HST] mythology/history mismatch · [LOG] logical contradiction

## §0-§1 Doctrine & Topology (1–10)
1. [LOG] The "intersection rule" (Keeper ∩ Watcher) assumes independence; LLMs share training data corpora, making failure modes correlated, violating the core premise of diverse redundancy.
2. [ARC] The 12-station pipeline is depicted as a mix of critical-path and parallel streams, but fails to specify the merge/reconciliation protocol if parallel streams (S4-S5, S7-S10) return conflicting modification directives for the same token.
3. [MTH] The "threshold, not wall" claim lacks a formal ROC curve analysis; without specified False Reject/Accept operating points, it is a metaphor, not a measurable design.
4. [SEC] DPoP tokens prevent replay but not token exfiltration; no mTLS or payload encryption specified for the Ingestion Gateway.
5. [PERF] No end-to-end latency budget summation provided. 12 stations with inter-station handoffs risk compounding queuing delays (Little's Law violation if pool sizes unbounded).
6. [HST] Mapping Grok to "Pazuzu-as-Protector" contradicts v0.5 formalism where Pazuzu's protection inherently backfires (Eq 144). Grok should be the high-risk high-reward agent, mapping perfectly to the paradox.
7. [ALG] S1-S12 numbering implies sequential state mutation, but parallel streams imply functional purity; the architecture vacillates between an imperative pipeline and a dataflow graph.
8. [OBS] "t-digests, EVT p99" are listed as telemetry, but no schema is provided for how streaming digests are merged across distributed pipeline replicas.
9. [API] No versioning strategy for the pipeline itself (only /v1/ for API). If S5 logic changes, how is retroactive telemetry distinguished?
10. [ARC] The "quarantine handoff" to S11 from S3 implies S11 is a dead-letter queue, but S11 is later defined as an active transformation (sanitize/isolate). Namespace collision in "quarantine" semantics.

## S1 — Chimera Gate (11–22)
11. [ALG] Gating network G(x) = softmax(Wx) is a dense linear map; real MoE routers use noisy top-k gating to enforce load balancing. Spec is outdated.
12. [PERF] "Top-2 experts active, others idle (kept warm)"—kept warm on what? Cold-start latency for a 70B expert is seconds, not milliseconds. Standby pool sizing undefined.
13. [MTH] Pairwise disagreement D = 1 - cos(h_i, h_j) on hidden states is a poor proxy for semantic contradiction (orthogonal vectors can mean the same thing in unaligned spaces).
14. [ALG] Decomposing queries into sub-queries on high discord risks infinite recursion if sub-queries also trigger high discord.
15. [SEC] Expert dropout during training is mentioned, but no inference-time expert-fallback is specified if an expert OOMs or crashes.
16. [OBS] pazuzu_s1_gate_entropy is insufficient; need per-expert utilization rate to detect routing collapse.
17. [ALG] "Stitch with provenance tags"—stitching algorithm undefined. Concatenation? Attention-overlap? LLM-summary?
18. [MTH] Switch-Transformer auxiliary loss is mentioned, but its coefficient (typically 0.01) is highly sensitive and uncalibrated in spec.
19. [PERF] Routing uncertainty metric requires synchronous computation on all expert hidden states, violating the "sparse activation" performance claim.
20. [API] No endpoint to force-route to a specific expert for A/B testing or debugging.
21. [LOG] "Silent Steward" implies zero token emission during discord, but the spec says it decomposes and stitches. It is not silent; it is verbose.
22. [HST] "Chimera" implies biological fusion; MoE is a temporal switch, not a spatial fusion. The metaphor mismatches the math.

## S2 — Sexagesimal Turn (23–34)
23. [MTH] A ring of 60 macro-blocks of ≤512 tokens caps context at 30,720 tokens. Severely limited for modern RAG/agentic loops requiring 128k+.
24. [ALG] "Sparse bridge attention every 6th block"—attention pattern is static. True long-context handling requires dynamic attention (e.g., chunked prefix or streaming attention).
25. [PERF] "Rolling deep archive embedding"—summarization is lossy. How is the KL divergence between the original and the summary computed to guarantee "retention does not fray"?
26. [ALG] "Retrieval triggered by bridge-attention salience"—requires computing attention weights over cold CPU/pinned memory before fetching to GPU, inverting the standard memory-fetch compute order and stalling SMs.
27. [MTH] Retention probability R(k) = exp(-k/60 · λ) assumes exponential decay (memoryless). Human/LLM context forgetting is power-law (recency effect).
28. [OBS] pazuzu_s2_retention_probe via needle-in-haystack is an offline eval; online probing (injecting synthetic facts and querying later) is needed for live metrics.
29. [PERF] KV-cache tiering (hot/warm/cold) requires a complex async memory mover; no spec for handling a page fault if hot memory is requested while still migrating from warm.
30. [ALG] Rotation counter k increments per what? Per request? Per token? If per request, a multi-turn chat rotates arbitrarily mid-sentence.
31. [HST] Base-60 ring implies 360° closure. If context wraps around, block 1 attends to block 60. Is this desired, or is block 1 "born" and block 60 "dying" (cylinder topology, not ring)?
32. [MTH] "6° bridge" is geometric numerology. 360/60 = 6, but attention heads don't map to degrees.
33. [PERF] Summarizing oldest blocks requires an auxiliary model call, adding massive latency spikes during context shifts.
34. [API] No mechanism for the user to "pin" a macro-block (e.g., system prompt) to prevent it from being rotated and summarized.

## S3 — Dual Ward (35–46)
35. [ALG] Watcher scores 4 axes in [0,1]. How are these calibrated? LLM judges are notoriously miscalibrated (overconfident).
36. [PERF] Watcher runs async "one segment behind". If Watcher rejects segment n-1, segment n is already emitted to user. "Kill-switch on stream" only stops future emissions, cannot unsay past tokens.
37. [SEC] DeepSeek-R1 reasoning mode triggered on "low confidence"—but Grok generates the confidence score. A compromised Keeper can report high confidence to bypass the Watcher's deep reasoning.
38. [MTH] min(axes) ≥ 0.75 is a strict intersection (conjunction). If one axis is 0.74 and others are 1.0, it fails. A weighted linear combination or Pareto front is more robust.
39. [ALG] "One regeneration with tightened temperature"—tightening temperature on an already-failed generation often leads to safe but unhelpful (refusal) outputs.
40. [PERF] Grok unavailable → DeepSeek-V3 assumes both roles. DeepSeek is fundamentally slower (R1 chain-of-thought); failover will violate p99 SLOs.
41. [SEC] "Watermarked ward:degraded"—watermarking is trivially spoofable if the API response schema is public.
42. [ALG] "Watcher compromised/returning garbage" → detected by audit-distribution drift. This requires a sustained window of bad outputs (Byzantine quorum). A sophisticated attack spaces out poison to stay under the drift threshold.
43. [LOG] Intersection rule claims "only intersection is spoken", yet failover mode allows "Keeper speaks alone". The core law is violated by the failover design.
44. [OBS] pazuzu_s3_false_reject_rate cannot be computed without ground-truth human override labels, which are not specified in the telemetry pipeline.
45. [PERF] 250ms budget for Watcher is unrealistic for R1 model (chain-of-thought) on complex prompts; will timeout constantly, forcing degraded mode.
46. [HST] Mythology: Pazuzu and Lamashtu are enemies, not independent auditors. A true mythological mapping would have the Watcher actively trying to subvert the Keeper, requiring a minimax game, not a passive audit.

## S4 — Swarm Agreement (47–56)
47. [ALG] Spawn 3-5 continuations → medoid selection. Medoid computation is O(N²) distance matrix; expensive for large embedding spaces.
48. [PERF] Speculative branches for early-exit consensus require duplicate KV caches; memory overhead is 3-5x, unaccounted for in deployment sizing.
49. [ALG] "Tie-break by Watcher score" introduces S3 dependency into S4, violating the stated parallelism of S4-S5/S7-S10.
50. [SEC] Seed + routing record for POST /v1/replay allows attackers to reverse-engineer routing thresholds by binary searching for expert activation boundaries.
51. [MTH] Aligned-cluster scoring assumes semantic truth equals consensus. In adversarial domains (e.g., math puzzles), the correct answer is often an outlier.
52. [PERF] "Wait-for-all" vs "early-exit"—spec claims both. Which is it? Early exit implies non-determinism (fastest branch wins, not best).
53. [OBS] pazuzu_s4_cluster_dispersion doesn't track which clusters lost; needed for offline S1 expert re-weighting.
54. [ALG] Consensus fan-out lacks a "self-consistency" check (generations must agree with themselves, not just each other).
55. [ALG] Replay determinism requires exact hardware float-point equivalence (GPU non-determinism), which is impossible across different cluster nodes.
56. [API] /v1/swarm is non-streaming only; no spec for progressive consensus (e.g., streaming medoid updates).

## S5 — Vector Current (57–68)
57. [MTH] Divergence ∇·v on a discrete sequence of embeddings is a finite difference approximation. In high-D space, this is extremely noisy and prone to curse of dimensionality.
58. [MTH] Curl |∇×v| is only defined in 3D. Embeddings are d >> 3. The cross-product is undefined. This is a fatal mathematical error in the core formalism.
59. [ALG] "Injecting top-3 archive blocks" on high divergence is a heuristic. What if the divergence is caused by a necessary pivot (e.g., user asks to change subject)? Re-anchoring will frustrate user intent.
60. [PERF] Embedding every emitted segment on the critical path adds ~5-10ms per token (forward pass of embedding model), destroying streaming throughput.
61. [MTH] Pairwise cross products of consecutive displacements implies orientation. Embedding spaces are orientation-ambiguous (sign flips are isomorphic).
62. [OBS] Live quiver plot on dashboard for high-dimensional trajectories requires t-SNE/UMAP reduction; computing this live is computationally prohibitive and will lag.
63. [ALG] "Ruin prevented before it takes flight"—but the divergence is measured after emission (since it's calculated on embeddings of emitted tokens). It's post-hoc correction, not prevention.
64. [SEC] Embedding trajectory exposes internal semantic geometry to the API consumer, aiding adversarial prompt optimization (gradient-free black box).
65. [LOG] S5 corrects drift, S10 corrects fracture. No defined hierarchy if both trigger on the same segment.
66. [API] GET /v1/field exposes raw diagnostics; no auth scope specified. Should be admin-only.
67. [ALG] Re-anchoring logic assumes S2 archive blocks are topically relevant; they might just be old system prompts.
68. [HST] "Wind field map" metaphor implies laminar/turbulent flow. Embedding trajectories do not conserve mass or energy, breaking the fluid dynamics analogy.

## S6 — Thermodynamic Brake (69–78)
69. [ALG] PD controller T_{t+1} = T_t exp[-κ_e(H_t - H*) - κ_d Ḣ_t]—derivative term Ḣ_t on discrete entropy is highly volatile; will cause temperature oscillations ("hunting").
70. [MTH] Output-token entropy H_t = -Σp_i log p_i is computed over the vocabulary. A low entropy does not mean "mode collapse" if the prompt is deterministic (e.g., "What is 2+2?"). Controller will artificially inflate temperature on factual queries.
71. [ALG] "Tighten nucleus-top-p" alongside temperature is redundant; temperature scales the logits, top-p truncates the tail. Their interaction is non-linear and uncalibrated.
72. [PERF] Anti-windup clip is applied post-hoc. True anti-windup requires back-calculation of the integral term; spec is incomplete.
73. [OBS] No telemetry for controller stability (gain/phase margin).
74. [ALG] Sliding window for entropy is fixed size; long creative generations will have different optimal windows than short factual ones.
75. [MTH] Target entropy H* is static. Ideal entropy is context-dependent (high for brainstorming, low for coding).
76. [SEC] Manipulating temperature based on output entropy allows an attacker to craft prompts that force the controller into a high-entropy loop, exhausting token limits.
77. [LOG] "Entropy governor" implies it governs the system, but it only governs the sampling distribution. It does not affect the model weights or context.
78. [HST] "Thermodynamics" metaphor is false (source truncated mid-issue; full text not supplied — see GAP_ANALYSIS).

## NOT SUPPLIED
- Issues #79–#144 (source truncated at #78).
- Enhancements E1–E96 (none supplied).
- The "eight fatal defects" are referenced but the source does not enumerate which of the 144 are fatal; do NOT assign fatal status without source evidence.
