# PAZUZU VM v1.0 — Source notes (CONDENSED)
# Two copies of the VM doc were supplied; they are nearly identical (second copy
# fixes one LaTeX typo in Eq 6). Both truncated ("...95 lines left" after §VI item 68).
# Treat equations below as the formalism registry source. Flag anything
# dimensionally inconsistent or non-computable as REVIEW_REQUIRED.

## §0 Foundational
- Pentadic State C = (σ, ρ, r, q, NL, β2, β3, Ψ); append-only event fold; "rollback" = compensating transaction (anti-event).
- Thaumic free energy F[C] = ∫[½(∇C)² + V(C) + κ_F(−C ln C) + ‖∇S_thaum‖²]dV; ops must descend F.
- hbar_thaum ≈ 1.05e-7 J·s (stipulated "Thaumic Planck constant" — NOT a measured physical constant; label as stipulated).
- E_ref ≈ 1e-12 J/op via "Mana-FLOP AMM" (market metaphor, not a market; label as stipulated).
- Lambda_0 ≈ 1e-3 J/m⁴ "Netherworld barrier tension" (stipulated).

## I. Thaumic Thermodynamics (selected)
1. Landauer spell erasure: E_mana ≥ k_B T ln2 · N_bits (applies ONLY to dealloc ops).
2. Itô mana dynamics: dM = (R_regen − C_spell·F_ops)dt + σM dW_t (reflecting boundary at 0).
4. Mana-FLOP AMM: x·y = k_pool (constant-product; computational interpretation: resource exchange curve).
8. Bekenstein bound of summoning: S ≤ 2πkRE/(ħc) (uses E=mc²+E_kinetic).
10. Wasserstein mana flow: JKO gradient flow (Ohm's law as linearization — honest analogy).

## II. Lexical Compilation (selected)
13. Incantation lexing; 14. Spell AST with CWT claims {iss, aud, exp, jti}; 15. Effect type system (contraction semantics); 17. Pure vs impure (divination impure); 20. Paradox exceptions → compensating transaction; 24. SLSA-attested linker (sigstore).

## III. Sympathetic Topology (selected)
25-26. Pointer binding, asymmetric contagion; 29. Weak refs; 32. Copy vs reference via GC reachability; 35. Leak = RC>0 ∧ ¬Reachable; 36. GC roots explicit.

## IV. Leyline Routing (selected)
37. Divergence ∇·J_ley = σ_node; 38. Curl ∇×J_ley = ω_nexus, threshold ‖ω‖ > hbar_thaum/A_node (NOTE: in 3D graph-embedding only; flag if generalized); 39. Wasserstein optimal routing; 42. GCRA drop probability; 43. BLS12-381 aggregate signatures.

## V. Scrying & Telemetry (selected)
49. DP scrying: I = H(X) − H(X|O+noise) with ε-DP bound; 50. "Thaumic uncertainty" ΔxΔp ≥ hbar_thaum/2 (ANALOGY — not quantum mechanics; label clearly); 55. Event replay = backward event fold; 56. Scrying as measurement (partial trace).

## VI. Warding & Cryptography (selected)
61. Port-Hamiltonian ward dynamics, dH/dt ≤ 0; 64. Ed25519ctx domain separation; 65. Bounded-depth FHE (depth ≤ D_max — honest); 67. BLS threshold ward with rogue-key defense.

## Honesty rules for implementation
- hbar_thaum, E_ref, Lambda_0 are STIPULATED parameters, not physical constants. Never present as physics.
- "Teleportation", "mana exchanges", "quantum" ops: implement as named abstract operations with documented semantics, NOT as physical claims.
- Dimensionally inconsistent equations → registry status REVIEW_REQUIRED, no implementation.
- Mythological terms (mana, wards, leylines, scrying) are domain labels for computational constructs.
