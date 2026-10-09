# PAZUZU-API v2.0

A twelve-station governed inference pipeline. Each request passes through a
sequence of stations — verification, memory, consensus, safety — that each emit
a provenance-carrying `StationOutput` defined by the shared contracts in
`packages/contracts/`.

## The twelve stations

| ID  | Name                | Module                    |
|-----|---------------------|---------------------------|
| S1  | Chimera Gate        | `stations/s01_chimera`        |
| S2  | Sexagesimal Turn    | `stations/s02_sexagesimal`    |
| S3  | Dual Ward           | `stations/s03_dual_ward`      |
| S4  | Swarm Agreement     | `stations/s04_swarm`          |
| S5  | Vector Current      | `stations/s05_vector_current` |
| S6  | Thermodynamic Brake | `stations/s06_thermodynamic_brake` |
| S7  | Breath Divider      | `stations/s07_breath_divider` |
| S8  | Living Memory       | `stations/s08_living_memory`  |
| S9  | Parallel Paths      | `stations/s09_parallel_paths` |
| S10 | Divergence Cut      | `stations/s10_divergence_cut` |
| S11 | Pattern Quarantine  | `stations/s11_pattern_quarantine` |
| S12 | Bronze Reduction    | `stations/s12_bronze_reduction` |

> S1–S6 display names follow the v1 audit nomenclature. S7–S12 names above are
> placeholders derived from their module directory names; the authoritative
> display name for each station lives in its `StationManifest.name`.

## Quickstart

```bash
cp .env.example .env          # mock mode is on by default — no keys needed
./scripts/dev.sh              # docker compose up --build
```

- API: http://localhost:8000
- Dashboard: http://localhost:3000
- Postgres: localhost:5432, Redis: localhost:6379

## Dev mode

Dev mode uses **deterministic mock providers**: `PAZUZU_MOCK_PROVIDERS=true`
(default in `.env.example`). Every station runs against fixed, seeded mock
LLM responses — no paid API keys required, and runs are reproducible.
Set `PAZUZU_MOCK_PROVIDERS=false` and supply `GROK_API_KEY` /
`DEEPSEEK_API_KEY` to hit real providers.

Mock outputs are labeled as mocks in provenance metadata and must never be
presented as real provider behavior.

## Repo layout

```
apps/api/            FastAPI gateway + orchestration endpoints
apps/dashboard/      Next.js operator console (execution graphs, station traces)
packages/contracts/  Pydantic v2 (Python) + TypeScript mirror of all data contracts
packages/client-sdk/ Typed client SDK (planned — NOT_IMPLEMENTED)
services/            gateway, orchestrator, providers, memory, verifier, quarantine, telemetry
stations/s01..s12    The twelve station implementations (each implements Station ABC)
vm/                  compiler, runtime, state, topology, simulation, formalism_registry
migrations/          Alembic schema migrations
tests/               unit, property, integration, e2e, security, benchmarks
docs/                architecture, api, threat model, benchmarks, audit resolution
scripts/dev.sh       convenience: docker compose up --build
```

## Honesty statement

- All provider interactions in dev/mock mode are **labeled mocks**; mock
  outputs carry `provider: "mock"` in provenance.
- This repository contains **no invented benchmarks or performance claims**.
  Any number reported from `tests/benchmarks/` is a measured run with its
  commit, hardware, and seed recorded alongside it. Unmeasured claims do not
  belong in docs or dashboards.
- Station interfaces are fixed by the contracts (`packages/contracts/`).
  Station internals must follow them; the README is not authoritative over the
  Pydantic models.

## Status

Repo scaffold (v2.0). Backend logic, stations, services, and tests are being
built by dedicated agents against the contracts.
