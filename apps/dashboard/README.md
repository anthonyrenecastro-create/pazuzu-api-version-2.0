# PAZUZU v2 — Intelligence Dashboard

Next.js 14 (app router) operations console for PAZUZU-API v2.0.

## Run

```bash
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL
npm run dev                        # http://localhost:3000
```

API base: `process.env.NEXT_PUBLIC_API_URL`, default `http://localhost:8000`.

## Honesty contract

Every page attempts the real backend endpoint **first**. When the backend is
unreachable (or a route is missing), the page falls back to a local fixture —
and the fixture is **always** flagged with a visible `DEMO` badge. No live
statistics are ever fabricated.

## Pages

| Route | View | Backend sources |
|---|---|---|
| `/` | Intelligence Console: prompt → `POST /v2/generate`, SSE stream viewer (`POST /v2/stream`) with candidate/approved/withheld/revised/rejected/completed/error events, Keeper/Watcher chips, verification panel, provenance inspector | `/v2/generate`, `/v2/stream`, `/v2/status` |
| `/observatory` | Twelve-Station Observatory: reactflow graph S1–S12, critical path highlighted, per-station status/duration, click → detail drawer (data/telemetry/provenance/warnings) | `/v2/stations`, `/v2/executions/latest` |
| `/wind` | Wind Field Observatory: S05 drift trajectory line chart, contradiction markers, branch comparison | `/v2/executions/latest` → S05, `/v2/wind` fallback |
| `/ward` | Dual Ward Chamber: candidate text, 4-axis score bars, decision badge, revision history | `/v2/ward/latest` |
| `/memory` | Sexagesimal Memory Ring: 60-segment SVG ring (hot/warm/cold), pinned markers, retrieval events, full CRUD | `/v2/memory` |
| `/swarm` | Swarm & Parallel Paths: candidate cards, consensus clusters, branch provenance tree | `/v2/swarm/latest` |
| `/quarantine` | Quarantine Chamber: record table + review actions (`POST /v2/quarantine/{id}/review`) with reason input; admin note | `/v2/quarantine` |
| `/bronze` | Bronze Reduction Lab: latency/resource/quality charts + optimization configs | `/v2/metrics` |
| `/vm` | VM Lab: source editor → compile (AST/errors) → simulate (events/invariants); formalism registry with verification badges | `/v2/vm/compile`, `/v2/vm/simulate`, `/v2/formalisms` |
| `/audit` | Audit & Enhancement Observatory: S001–S078 records, GAP #79–144 section, enhancements panel (honest "not supplied") | `/v2/audit` |

## Shared

- `lib/api.ts` — typed fetch helpers (`apiGet`/`apiPost`/`apiDelete`/`streamPost`) with DEMO fallback flagging. Types imported from `packages/contracts/typescript`.
- `lib/types.ts` — dashboard-side interfaces for backend-defined shapes.
- `lib/fixtures.ts` — labeled demo fixtures, used only on fetch failure.
- `components/StatusPill.tsx`, `components/DemoBadge.tsx`, `components/Nav.tsx`.

Theme: dark bronze (deep browns, bronze/gold accents), minimal.
