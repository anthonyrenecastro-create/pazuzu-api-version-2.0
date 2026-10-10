"""Formalism registry entries sourced from _source/vm_notes.md.

Each entry records: id, title, source_equation, symbols, units,
computational_interpretation, assumptions, limitations, implementation_ref,
verification_status, and whether it is an analogy.

verification_status values:
  IMPLEMENTED_TESTED      implemented AND covered by an automated test
  IMPLEMENTED_UNVERIFIED  implemented but not yet test-covered
  REVIEW_REQUIRED         dimensionally inconsistent, non-computable as stated,
                          or otherwise needing review — NEVER implemented
  NOT_IMPLEMENTED         understood, deliberately not built (reason in limitations)

Honesty rules (from the source notes):
  * hbar_thaum, E_ref, Lambda_0 are STIPULATED parameters, never physical constants.
  * "Teleportation" / "mana exchange" are named abstract ops, NOT physical claims.
  * Dimensionally inconsistent equations get REVIEW_REQUIRED, never implemented.
  * Mythological terms are domain labels for computational constructs.
"""

from __future__ import annotations

ENTRIES: list[dict] = [
    {
        "id": "FOUND-00",
        "title": "Pentadic state with append-only event fold",
        "source_equation": "vm_notes §0: C = (σ, ρ, r, q, NL, β2, β3, Ψ); state = fold(events)",
        "symbols": {"C": "pentadic state tuple", "events": "append-only log"},
        "units": {},
        "computational_interpretation": (
            "Event-sourced state: the VM never mutates state in place; the "
            "current state is the left fold of the event log from event 0."
        ),
        "assumptions": ["fold function is deterministic", "events are totally ordered by seq"],
        "limitations": ["fold cost is O(n) in log length; snapshots mitigate"],
        "implementation_ref": "vm/state/store.py",
        "verification_status": "IMPLEMENTED_TESTED",
        "analogy": False,
    },
    {
        "id": "FOUND-00b",
        "title": "Compensating transactions (anti-events)",
        "source_equation": "vm_notes §0 + Eq 20: 'rollback' = compensating transaction",
        "symbols": {"anti-event": "event reversing a prior event's effect"},
        "units": {},
        "computational_interpretation": (
            "No delete/rollback primitive. Engine.compensate(seq) appends an "
            "anti-event (e.g. bind.restore, banish.restore) that reverses the "
            "target event's effect when folded."
        ),
        "assumptions": ["anti-event defined for the target event type"],
        "limitations": ["only bind.set and banish.tombstone have anti-events today"],
        "implementation_ref": "vm/runtime/engine.py",
        "verification_status": "IMPLEMENTED_TESTED",
        "analogy": False,
    },
    {
        "id": "THERM-01",
        "title": "Landauer spell erasure bound",
        "source_equation": "vm_notes §I Eq 1: E_mana ≥ k_B T ln2 · N_bits",
        "symbols": {"E_mana": "mana energy", "N_bits": "erased bits", "T": "temperature"},
        "units": {"E_mana": "J (stipulated)", "k_B T": "J", "N_bits": "dimensionless"},
        "computational_interpretation": (
            "Lower bound on the resource cost of deallocation ops. Applies "
            "ONLY to dealloc ops."
        ),
        "assumptions": ["thermal equilibrium at T", "irreversible erasure"],
        "limitations": [
            "The DSL has no dealloc op, so the bound has no application point; "
            "not implemented rather than misapplied."
        ],
        "implementation_ref": None,
        "verification_status": "NOT_IMPLEMENTED",
        "analogy": False,
    },
    {
        "id": "THERM-02",
        "title": "Itô mana dynamics with reflecting boundary",
        "source_equation": "vm_notes §I Eq 2: dM = (R_regen − C_spell·F_ops)dt + σM dW_t, reflecting at 0",
        "symbols": {"M": "mana balance", "R_regen": "regen rate", "C_spell": "cost rate",
                    "W_t": "Wiener process"},
        "units": {"M": "mana units", "t": "s"},
        "computational_interpretation": (
            "Stochastic mana balance model. Would require Euler–Maruyama "
            "discretization with a reflecting boundary scheme."
        ),
        "assumptions": ["Itô interpretation", "reflecting boundary implementable without bias"],
        "limitations": [
            "Discretization + reflecting-boundary handling unverified in this VM; "
            "naive Euler steps leak probability mass at the boundary. "
            "Engine uses exact discrete charge events instead."
        ],
        "implementation_ref": None,
        "verification_status": "REVIEW_REQUIRED",
        "analogy": False,
    },
    {
        "id": "THERM-04",
        "title": "Mana-FLOP constant-product exchange curve",
        "source_equation": "vm_notes §I Eq 4: x·y = k_pool",
        "symbols": {"x": "pool A reserve", "y": "pool B reserve", "k_pool": "invariant"},
        "units": {"x": "mana units", "y": "mana units"},
        "computational_interpretation": (
            "Constant-product curve governing the abstract mana_exchange op: "
            "amount_in leaves pool A, the curve sets what arrives in pool B."
        ),
        "assumptions": ["pools are fungible within the simulation"],
        "limitations": [
            "Labeled a 'market metaphor' in the source notes — it is NOT a market. "
            "No price discovery, no external liquidity."
        ],
        "implementation_ref": "vm/runtime/opcodes.py",
        "verification_status": "IMPLEMENTED_UNVERIFIED",
        "analogy": True,
    },
    {
        "id": "THERM-08",
        "title": "Bekenstein bound of summoning",
        "source_equation": "vm_notes §I Eq 8: S ≤ 2πkRE/(ħc), with E = mc² + E_kinetic",
        "symbols": {"S": "entropy", "R": "radius", "E": "energy"},
        "units": {"S": "J/K", "R": "m", "E": "J"},
        "computational_interpretation": "None implemented. An information-capacity bound.",
        "assumptions": ["relativistic regime", "spherical region"],
        "limitations": [
            "Mixes E=mc² with a non-relativistic VM resource model; applying it "
            "to 'summoning' (object instantiation) would be a physical claim "
            "about computation. Not implemented."
        ],
        "implementation_ref": None,
        "verification_status": "REVIEW_REQUIRED",
        "analogy": False,
    },
    {
        "id": "THERM-10",
        "title": "Wasserstein mana flow (JKO gradient flow)",
        "source_equation": "vm_notes §I Eq 10: JKO gradient flow; Ohm's law as linearization",
        "symbols": {"J": "mana flux"},
        "units": {},
        "computational_interpretation": (
            "Mana redistribution modeled as gradient flow in Wasserstein space. "
            "Source notes explicitly mark the Ohm linearization as an honest analogy."
        ),
        "assumptions": ["mana density is a probability measure", "JKO time-stepping converges"],
        "limitations": [
            "JKO stepping is unverified in this codebase; routing uses Dijkstra "
            "on explicit graphs instead. Analogy only."
        ],
        "implementation_ref": None,
        "verification_status": "REVIEW_REQUIRED",
        "analogy": True,
    },
    {
        "id": "LEX-13",
        "title": "Incantation lexing",
        "source_equation": "vm_notes §II Eq 13: incantation lexing",
        "symbols": {},
        "units": {},
        "computational_interpretation": (
            "Tokenizer for the thaumic DSL: op names, identifiers, numbers with "
            "unit suffixes, strings, brackets, arrows, comments; line/col tracking."
        ),
        "assumptions": ["UTF-8 source text"],
        "limitations": ["single dialect (thaumic-1); no macro expansion"],
        "implementation_ref": "vm/compiler/lexer.py",
        "verification_status": "IMPLEMENTED_TESTED",
        "analogy": False,
    },
    {
        "id": "LEX-14",
        "title": "Spell AST with attested claims",
        "source_equation": "vm_notes §II Eq 14: Spell AST with CWT claims {iss, aud, exp, jti}",
        "symbols": {"iss": "issuer", "aud": "audience", "exp": "expiry", "jti": "token id"},
        "units": {},
        "computational_interpretation": (
            "Parser produces a typed AST. The CWT-claims envelope (iss/aud/exp/jti) "
            "is specified but not yet attested — ASTs are currently unsigned dicts."
        ),
        "assumptions": [],
        "limitations": ["no signature/attestation on ASTs yet; claims envelope unimplemented"],
        "implementation_ref": "vm/compiler/parser.py",
        "verification_status": "IMPLEMENTED_UNVERIFIED",
        "analogy": False,
    },
    {
        "id": "LEX-15",
        "title": "Effect type system (contraction semantics)",
        "source_equation": "vm_notes §II Eq 15: effect type system",
        "symbols": {},
        "units": {},
        "computational_interpretation": (
            "Each op declares purity + effect tags (reads_state, writes_state, "
            "observes, consumes_mana). The checker rejects unknown ops, arity "
            "violations, and non-statically-known mana costs."
        ),
        "assumptions": ["all ops in OP_NAMES are classified"],
        "limitations": ["no higher-order effects; guards pure by construction"],
        "implementation_ref": "vm/compiler/effects.py",
        "verification_status": "IMPLEMENTED_TESTED",
        "analogy": False,
    },
    {
        "id": "LEX-17",
        "title": "Pure vs impure op classification",
        "source_equation": "vm_notes §II Eq 17: divination is impure",
        "symbols": {},
        "units": {},
        "computational_interpretation": (
            "scry (divination/observation) is classified impure: it reads state "
            "and performs observation. All seven DSL ops are impure; purity is "
            "enforced structurally for if-guards."
        ),
        "assumptions": [],
        "limitations": [],
        "implementation_ref": "vm/compiler/effects.py",
        "verification_status": "IMPLEMENTED_TESTED",
        "analogy": False,
    },
    {
        "id": "LEX-24",
        "title": "SLSA-attested linker",
        "source_equation": "vm_notes §II Eq 24: SLSA-attested linker (sigstore)",
        "symbols": {},
        "units": {},
        "computational_interpretation": "Supply-chain attestation for linked spell artifacts.",
        "assumptions": ["sigstore infrastructure available"],
        "limitations": ["no linker exists yet; nothing to attest"],
        "implementation_ref": None,
        "verification_status": "NOT_IMPLEMENTED",
        "analogy": False,
    },
    {
        "id": "SYMP-25",
        "title": "Pointer binding / asymmetric contagion",
        "source_equation": "vm_notes §III Eq 25-26: pointer binding, asymmetric contagion",
        "symbols": {},
        "units": {},
        "computational_interpretation": (
            "bind writes name->value into the reference table (folded from "
            "bind.set events). Weak refs / contagion rules not modeled."
        ),
        "assumptions": ["names are strings", "single global reference table per engine"],
        "limitations": ["no weak references (Eq 29), no GC reachability (Eq 32/35/36)"],
        "implementation_ref": "vm/runtime/opcodes.py",
        "verification_status": "IMPLEMENTED_TESTED",
        "analogy": False,
    },
    {
        "id": "SYMP-32",
        "title": "Copy vs reference via GC reachability",
        "source_equation": "vm_notes §III Eq 32, 35, 36: leak = RC>0 ∧ ¬Reachable; explicit GC roots",
        "symbols": {"RC": "reference count"},
        "units": {},
        "computational_interpretation": "Garbage-collector semantics for bindings.",
        "assumptions": [],
        "limitations": ["no GC implemented; bindings live until banished"],
        "implementation_ref": None,
        "verification_status": "NOT_IMPLEMENTED",
        "analogy": False,
    },
    {
        "id": "TOPO-37",
        "title": "Leyline divergence",
        "source_equation": "vm_notes §IV Eq 37: ∇·J_ley = σ_node",
        "symbols": {"J_ley": "leyline flow", "σ_node": "node source/sink term"},
        "units": {"flow": "capacity units"},
        "computational_interpretation": (
            "Divergence on a directed graph = inflow − outflow of edge "
            "capacities. Positive: net sink; negative: net source."
        ),
        "assumptions": ["capacities are non-negative"],
        "limitations": ["flow accounting only; no physics of 'leylines' implied"],
        "implementation_ref": "vm/topology/graph.py",
        "verification_status": "IMPLEMENTED_TESTED",
        "analogy": False,
    },
    {
        "id": "TOPO-38",
        "title": "Leyline curl threshold",
        "source_equation": "vm_notes §IV Eq 38: ∇×J_ley = ω_nexus, threshold ‖ω‖ > hbar_thaum/A_node",
        "symbols": {"ω_nexus": "vorticity", "A_node": "node area"},
        "units": {"hbar_thaum": "J·s (STIPULATED)", "A_node": "m²"},
        "computational_interpretation": "None — deliberately not implemented.",
        "assumptions": ["requires a 2D/3D embedding with faces and orientation"],
        "limitations": [
            "The source notes restrict this to '3D graph-embedding only'. A "
            "discrete curl on a general graph has no canonical definition "
            "(Stokes' theorem needs faces/orientation). Generalizing the "
            "formula would be dimensionally and mathematically unsound — the "
            "same fatal-math rule as the S5 attempt. NOT_IMPLEMENTED by design."
        ],
        "implementation_ref": None,
        "verification_status": "NOT_IMPLEMENTED",
        "analogy": False,
    },
    {
        "id": "TOPO-39",
        "title": "Wasserstein-optimal routing",
        "source_equation": "vm_notes §IV Eq 39: Wasserstein optimal routing",
        "symbols": {},
        "units": {},
        "computational_interpretation": (
            "Optimal-transport routing over the leyline graph. The engine "
            "implements Dijkstra shortest-path on explicit topology instead."
        ),
        "assumptions": [],
        "limitations": [
            "Dijkstra is shortest-path, not Wasserstein-optimal; the "
            "optimality claim is unverified here."
        ],
        "implementation_ref": "vm/topology/graph.py",
        "verification_status": "REVIEW_REQUIRED",
        "analogy": True,
    },
    {
        "id": "TOPO-42",
        "title": "GCRA drop probability",
        "source_equation": "vm_notes §IV Eq 42: GCRA drop probability",
        "symbols": {},
        "units": {},
        "computational_interpretation": "Generic Cell Rate Algorithm policing for flows.",
        "assumptions": [],
        "limitations": ["no traffic policing implemented"],
        "implementation_ref": None,
        "verification_status": "NOT_IMPLEMENTED",
        "analogy": False,
    },
    {
        "id": "SCR-49",
        "title": "Differentially-private scrying",
        "source_equation": "vm_notes §V Eq 49: I = H(X) − H(X|O+noise), ε-DP bound",
        "symbols": {"ε": "privacy budget", "O": "observation"},
        "units": {},
        "computational_interpretation": (
            "Scrying as a noisy observation channel with an ε-DP bound on "
            "information leakage."
        ),
        "assumptions": ["noise mechanism calibrated to sensitivity"],
        "limitations": [
            "The scry op records observations WITHOUT noise; the ε-DP bound "
            "is unimplemented and unverified. Telemetry is exact."
        ],
        "implementation_ref": "vm/runtime/opcodes.py",
        "verification_status": "REVIEW_REQUIRED",
        "analogy": False,
    },
    {
        "id": "SCR-50",
        "title": "Thaumic uncertainty principle",
        "source_equation": "vm_notes §V Eq 50: ΔxΔp ≥ hbar_thaum/2",
        "symbols": {"hbar_thaum": "STIPULATED, ≈1.05e-7 J·s", "Δx": "position spread", "Δp": "momentum spread"},
        "units": {"hbar_thaum": "J·s (STIPULATED — not a physical constant)"},
        "computational_interpretation": (
            "ANALOGY. A lower bound on joint measurement precision, shaped "
            "like the quantum uncertainty relation but with a stipulated "
            "constant. It is NOT quantum mechanics and makes no physical claim."
        ),
        "assumptions": ["none — analogical framing only"],
        "limitations": [
            "MARKED ANALOGY. hbar_thaum is stipulated, not measured. "
            "Must never be presented as physics. REVIEW_REQUIRED before any "
            "computational use."
        ],
        "implementation_ref": None,
        "verification_status": "REVIEW_REQUIRED",
        "analogy": True,
    },
    {
        "id": "SCR-55",
        "title": "Event replay as backward fold",
        "source_equation": "vm_notes §V Eq 55: event replay = backward event fold",
        "symbols": {},
        "units": {},
        "computational_interpretation": (
            "Replaying the log from event 0 reproduces state (EventStore.replay). "
            "'Backward' inspection is log traversal, not time travel."
        ),
        "assumptions": ["fold is deterministic"],
        "limitations": [],
        "implementation_ref": "vm/state/store.py",
        "verification_status": "IMPLEMENTED_TESTED",
        "analogy": False,
    },
    {
        "id": "SCR-56",
        "title": "Scrying as measurement (partial trace)",
        "source_equation": "vm_notes §V Eq 56: scrying as measurement / partial trace",
        "symbols": {},
        "units": {},
        "computational_interpretation": (
            "Observation modeled on the partial-trace idea: observing a "
            "subsystem discards the rest."
        ),
        "assumptions": [],
        "limitations": [
            "Analogical framing; the op is a plain table read plus telemetry. "
            "No Hilbert-space structure exists here."
        ],
        "implementation_ref": None,
        "verification_status": "REVIEW_REQUIRED",
        "analogy": True,
    },
    {
        "id": "WARD-61",
        "title": "Port-Hamiltonian ward dynamics",
        "source_equation": "vm_notes §VI Eq 61: port-Hamiltonian ward dynamics, dH/dt ≤ 0",
        "symbols": {"H": "ward Hamiltonian"},
        "units": {},
        "computational_interpretation": (
            "Wards as dissipative dynamical systems. The engine implements "
            "wards as permission predicates, not as dynamics."
        ),
        "assumptions": ["dissipativity dH/dt ≤ 0"],
        "limitations": [
            "Predicate implementation does not realize the dynamics; "
            "stability claims unverified."
        ],
        "implementation_ref": "vm/runtime/opcodes.py",
        "verification_status": "REVIEW_REQUIRED",
        "analogy": False,
    },
    {
        "id": "CRYPTO-43",
        "title": "BLS12-381 aggregate signatures",
        "source_equation": "vm_notes §IV Eq 43: BLS12-381 aggregate signatures",
        "symbols": {},
        "units": {},
        "computational_interpretation": "Aggregate signatures over sealed events.",
        "assumptions": ["BLS12-381 pairing library"],
        "limitations": [
            "Not implemented. seal uses HMAC-SHA256 with a per-run key, "
            "documented as simulation-internal tamper-evidence only."
        ],
        "implementation_ref": None,
        "verification_status": "NOT_IMPLEMENTED",
        "analogy": False,
    },
    {
        "id": "CRYPTO-64",
        "title": "Ed25519ctx domain separation",
        "source_equation": "vm_notes §VI Eq 64: Ed25519ctx domain separation",
        "symbols": {},
        "units": {},
        "computational_interpretation": "Domain-separated signatures for ward/seal artifacts.",
        "assumptions": [],
        "limitations": ["not implemented; see CRYPTO-43"],
        "implementation_ref": None,
        "verification_status": "NOT_IMPLEMENTED",
        "analogy": False,
    },
    {
        "id": "CRYPTO-65",
        "title": "Bounded-depth FHE",
        "source_equation": "vm_notes §VI Eq 65: bounded-depth FHE, depth ≤ D_max",
        "symbols": {"D_max": "max circuit depth"},
        "units": {},
        "computational_interpretation": "Homomorphic evaluation of ward predicates.",
        "assumptions": [],
        "limitations": ["not implemented; no FHE library wired in"],
        "implementation_ref": None,
        "verification_status": "NOT_IMPLEMENTED",
        "analogy": False,
    },
    {
        "id": "CRYPTO-67",
        "title": "BLS threshold ward with rogue-key defense",
        "source_equation": "vm_notes §VI Eq 67: BLS threshold ward, rogue-key defense",
        "symbols": {},
        "units": {},
        "computational_interpretation": "Threshold-authorized ward operations.",
        "assumptions": [],
        "limitations": ["not implemented; see CRYPTO-43"],
        "implementation_ref": None,
        "verification_status": "NOT_IMPLEMENTED",
        "analogy": False,
    },
    {
        "id": "ABS-TELEPORT",
        "title": "Teleportation (abstract op)",
        "source_equation": "n/a — named abstract operation",
        "symbols": {},
        "units": {},
        "computational_interpretation": (
            "ABSTRACT OP ONLY. op_teleport relabels a binding's location tag "
            "without traversing any path. It is a reference-table update and "
            "is NOT physical teleportation."
        ),
        "assumptions": ["name is bound"],
        "limitations": [
            "NOT_IMPLEMENTED as a DSL op; callable only via the abstract-op "
            "interface. Must never be described as physical."
        ],
        "implementation_ref": "vm/runtime/opcodes.py",
        "verification_status": "NOT_IMPLEMENTED",
        "analogy": True,
    },
]
