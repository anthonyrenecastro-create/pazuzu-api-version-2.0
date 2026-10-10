# PAZUZU Virtual Mechanics (VM) Subsystem

A small, honest virtual machine for the "thaumic" DSL: compile spells
(source text) to a typed AST, type-check effects, and execute them against
an **event-sourced** state model with capability-based permissions and
mana (resource) accounting.

## Layout

```
vm/
  compiler/lexer.py     tokenizer (op names, idents, numbers+units, strings,
                        brackets, ->, ;, # comments) with line/col errors
  compiler/parser.py    recursive-descent parser -> typed AST dicts
  compiler/ast.py       validation (unknown op / wrong arity), pretty-printer
  compiler/effects.py   effect type system: pure/impure + tags
                        (reads_state, writes_state, observes, consumes_mana);
                        consumes_mana ops need statically-known costs
  runtime/engine.py     event-sourced execution, compensating transactions,
                        capability tokens, mana accounting, clean halts,
                        seeded determinism
  runtime/opcodes.py    computable ops: bind, ward, scry, route, seal,
                        banish, attune (+ documented abstract stubs)
  state/store.py        in-memory event store: append, replay-from-0,
                        snapshot/restore
  state/invariants.py   mana non-negative, log append-only,
                        capability monotonicity, no tombstone resurrection
  topology/graph.py     leyline graph: divergence, Dijkstra routing
  simulation/runner.py  run(ast, initial_state, max_steps, seed)
                        -> VMSimulateResponse-shaped dict
  formalism_registry/   27 formalism entries from _source/vm_notes.md,
                        each graded IMPLEMENTED_TESTED / IMPLEMENTED_UNVERIFIED
                        / REVIEW_REQUIRED / NOT_IMPLEMENTED
  constants.py          stipulated parameters (see below)
```

## API wiring

- `vm.compile_source(source)` returns a `VMCompileResponse`-shaped dict
  (`ok`, `ast`, `errors`, `warnings`). The `ast` is consumable as the `ast`
  field of `VMCompileRequest` / `VMSimulateRequest`.
- `vm.simulate(ast, initial_state, max_steps, seed)` returns a
  `VMSimulateResponse`-shaped dict
  (`ok`, `final_state`, `events`, `invariant_checks`, `errors`).
- `max_steps` defaults to 1000, hard-capped at 100000.

Example:

```python
from vm import compile_source, simulate

res = compile_source('''
spell transit() {
  bind node_a = "alpha";
  bind node_b = "beta";
  route(node_a, node_b);
  seal("manifest");
}
''')
out = simulate(res["ast"], initial_state={
    "mana": {"caster": 100.0},
    "topology": {"nodes": ["alpha", "beta"],
                 "edges": [["alpha", "beta", 2.0]]},
})
```

## Honesty boundaries (read before extending)

1. **Stipulated parameters, not physics.** `HBAR_THAUM`, `E_REF`, `LAMBDA_0`
   in `constants.py` are internal simulation constants. They are not measured
   physical constants and must never be presented as such.
2. **Mythological terms are domain labels.** "Mana" = a resource-accounting
   number. "Wards" = permission predicates. "Leylines" = graph edges.
   "Scrying" = a table read plus telemetry. Nothing here claims anything
   about the physical world.
3. **Dimensionally-inconsistent or non-computable equations are never
   implemented.** They get `REVIEW_REQUIRED` in the formalism registry.
4. **No graph curl.** Source Eq 38's curl is restricted to a specific 3D
   graph embedding; a discrete curl on a general graph has no canonical
   definition (Stokes needs faces/orientation). We implement divergence and
   Dijkstra routing only — the same fatal-math rule as the S5 attempt.
5. **"Teleport" and "mana exchange" are named abstract ops**, documented in
   `runtime/opcodes.py` and registry entry `ABS-TELEPORT`. Teleport is a
   reference-table relabel; mana exchange is a constant-product curve. Neither
   is physical, neither is a market.
6. **The thaumic uncertainty relation (ΔxΔp ≥ ħ_thaum/2) is an ANALOGY**
   (registry `SCR-50`, `REVIEW_REQUIRED`). It is not quantum mechanics.
7. **Rollback = compensation.** The event log is append-only; undo is an
   anti-event, never deletion. `EventStore.restore()` is an operator/test
   action, not a runtime primitive.
8. **seal uses HMAC-SHA256 with a per-run key** as simulation-internal
   tamper-evidence. It is not BLS/Ed25519 (registry `CRYPTO-43`/`64`,
   `NOT_IMPLEMENTED`).
