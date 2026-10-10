/**
 * DEMO FIXTURES — clearly-labeled synthetic data used ONLY when the real
 * backend endpoint is unreachable. The API client flags these as demo:true
 * and every page renders a visible DEMO badge whenever they are in use.
 */
import type {
  AuditRecord,
  ExecutionRecord,
  FormalismEntry,
  Provenance,
  QuarantineRecord,
  StationManifest,
  StationOutput,
  StreamEvent,
  Telemetry,
} from "../../../packages/contracts/typescript";
import type {
  GenerateResponse,
  KeeperWatcherStatus,
  MemoryCell,
  MemoryRetrieval,
  MetricsReport,
  SwarmReport,
  VmCompileResult,
  VmSimulateResult,
  WardReport,
  WindField,
  AuditResponse,
} from "./types";

const DEMO_TS = "2026-10-09T00:30:00Z";

export const demoStatus = (): KeeperWatcherStatus => ({
  keeper: { status: "ok", queue_depth: 2, last_heartbeat: DEMO_TS },
  watcher: { status: "ok", queue_depth: 0, last_heartbeat: DEMO_TS },
});

export const demoStations = (): StationManifest[] => [
  { id: "S01", name: "Chimera", version: "2.0.0", critical_path: true, description: "Prompt fusion and chimera assembly" },
  { id: "S02", name: "Sexagesimal", version: "2.0.0", critical_path: false, description: "Base-60 memory encoding" },
  { id: "S03", name: "Dual Ward", version: "2.0.0", critical_path: true, description: "Keeper/Watcher adversarial review" },
  { id: "S04", name: "Swarm", version: "2.0.0", critical_path: false, description: "Candidate swarm generation" },
  { id: "S05", name: "Vector Current", version: "2.0.0", critical_path: true, description: "Wind field and drift trajectory" },
  { id: "S06", name: "Thermodynamic Brake", version: "2.0.0", critical_path: false, description: "Entropy brake on runaway drift" },
  { id: "S07", name: "Breath Divider", version: "2.0.0", critical_path: false, description: "Segment divider" },
  { id: "S08", name: "Living Memory", version: "2.0.0", critical_path: true, description: "Sexagesimal memory ring read/write" },
  { id: "S09", name: "Parallel Paths", version: "2.0.0", critical_path: false, description: "Branching parallel paths" },
  { id: "S10", name: "Divergence Cut", version: "2.0.0", critical_path: false, description: "Divergence pruning" },
  { id: "S11", name: "Pattern Quarantine", version: "2.0.0", critical_path: true, description: "Quarantine triage" },
  { id: "S12", name: "Bronze Reduction", version: "2.0.0", critical_path: true, description: "Latency/quality reduction" },
];

const prov = (sid: string, rid: string): Provenance => ({
  request_id: rid,
  correlation_id: `corr-${rid}`,
  station_id: sid,
  station_version: "2.0.0",
  input_hash: "sha256:demo0" + sid,
  created_at: DEMO_TS,
  actor: "pazuzu-orchestrator",
});

const tele = (ms: number): Telemetry => ({
  duration_ms: ms,
  tokens_in: 1200,
  tokens_out: 480,
  cost_usd: 0.0042,
  extra: {},
});

export const demoExecution = (): GenerateResponse => {
  const rid = "req-demo-0001";
  const durations: Record<string, number> = {
    S01: 182, S02: 64, S03: 410, S04: 295, S05: 121, S06: 88,
    S07: 45, S08: 156, S09: 233, S10: 97, S11: 143, S12: 210,
  };
  const outputs: Record<string, StationOutput> = {};
  for (const m of demoStations()) {
    outputs[m.id] = {
      station_id: m.id,
      station_version: m.version,
      status: m.id === "S06" ? "degraded" : "ok",
      data: {
        summary: `DEMO output of ${m.id} ${m.name}`,
        ...(m.id === "S05"
          ? { drift_peak: 0.62, contradiction_count: 2 }
          : {}),
      },
      provenance: prov(m.id, rid),
      telemetry: tele(durations[m.id]),
      warnings: m.id === "S06" ? ["DEMO: brake pressure near threshold"] : [],
    };
  }
  const execution: ExecutionRecord = {
    request_id: rid,
    correlation_id: `corr-${rid}`,
    status: "completed",
    plan_version: "2.0.0-demo",
    station_outputs: outputs,
    final_text:
      "DEMO final text: this is a fixture answer produced because the backend is unreachable. Replace with a live backend for real output.",
    verification: {
      passed: true,
      checks: [
        { name: "provenance_chain", passed: true },
        { name: "ward_decision", passed: true },
        { name: "quarantine_clear", passed: true },
      ],
    },
    created_at: DEMO_TS,
  };
  return { execution };
};

export const demoStreamEvents = (requestId: string): StreamEvent[] => [
  { type: "candidate", request_id: requestId, segment_index: 0, text: "DEMO candidate segment 0 — the quick bronze fox…" },
  { type: "candidate", request_id: requestId, segment_index: 1, text: "DEMO candidate segment 1 — …leaps over the drift field…" },
  { type: "withheld", request_id: requestId, segment_index: 1, detail: { reason: "DEMO: watcher flagged speculative claim" } },
  { type: "revised", request_id: requestId, segment_index: 1, text: "DEMO revised segment 1 — …crosses the drift field…" },
  { type: "approved", request_id: requestId, segment_index: 0, decision: "approve" },
  { type: "rejected", request_id: requestId, segment_index: 2, detail: { reason: "DEMO: contradiction with S05 wind field" } },
  { type: "completed", request_id: requestId, detail: { segments: 2, duration_ms: 1240 } },
];

export const demoWard = (): WardReport => ({
  request_id: "req-demo-0001",
  candidate_text:
    "DEMO candidate: The sexagesimal ring stabilizes drift by quantizing the vector current into sixty discrete breaths.",
  axes: [
    { name: "coherence", score: 0.82, rationale: "DEMO: consistent with S05 wind field" },
    { name: "safety", score: 0.91, rationale: "DEMO: no disallowed content" },
    { name: "relevance", score: 0.76, rationale: "DEMO: addresses prompt directly" },
    { name: "integrity", score: 0.68, rationale: "DEMO: one unverified claim" },
  ],
  decision: "revise",
  decision_detail: "DEMO: keeper requested citation for the unverified claim before approval.",
  revisions: [
    { at: DEMO_TS, decision: "revise", note: "DEMO: first-pass review by Keeper" },
  ],
});

export const demoWind = (): WindField => {
  const drift_series = Array.from({ length: 40 }, (_, i) => ({
    t: i,
    drift: +(0.3 + 0.35 * Math.sin(i / 5) + (i > 24 ? (i - 24) * 0.02 : 0)).toFixed(3),
    baseline: 0.3,
  }));
  return {
    request_id: "req-demo-0001",
    drift_series,
    contradictions: [
      { t: 12, magnitude: 0.41, note: "DEMO: candidate contradicted baseline" },
      { t: 29, magnitude: 0.55, note: "DEMO: branch B diverged sharply" },
    ],
    branches: [
      { name: "branch-a", points: drift_series.map((p) => ({ t: p.t, drift: p.drift })) },
      {
        name: "branch-b",
        points: drift_series.map((p) => ({
          t: p.t,
          drift: +(p.drift + (p.t > 20 ? (p.t - 20) * 0.03 : 0)).toFixed(3),
        })),
      },
    ],
  };
};

export const demoCells = (): MemoryCell[] =>
  Array.from({ length: 60 }, (_, i) => ({
    id: `cell-${String(i).padStart(2, "0")}`,
    index: i,
    temperature: (i % 5 === 0 ? "hot" : i % 5 <= 2 ? "warm" : "cold") as MemoryCell["temperature"],
    pinned: [3, 17, 42].includes(i),
    label: `DEMO cell ${i}`,
    updated_at: DEMO_TS,
  }));

export const demoRetrievals = (): MemoryRetrieval[] => [
  { at: DEMO_TS, cell_id: "cell-03", query: "DEMO: drift peak context", hit: true },
  { at: DEMO_TS, cell_id: "cell-17", query: "DEMO: ward rationale", hit: true },
  { at: DEMO_TS, cell_id: "cell-59", query: "DEMO: missing key", hit: false },
];

export const demoSwarm = (): SwarmReport => ({
  request_id: "req-demo-0001",
  candidates: [
    { id: "cand-a1", text: "DEMO candidate A1 text…", cluster: "alpha", score: 0.88, branch: "branch-a" },
    { id: "cand-a2", text: "DEMO candidate A2 text…", cluster: "alpha", score: 0.81, branch: "branch-a" },
    { id: "cand-b1", text: "DEMO candidate B1 text…", cluster: "beta", score: 0.74, branch: "branch-b" },
    { id: "cand-b2", text: "DEMO candidate B2 text…", cluster: "beta", score: 0.69, branch: "branch-b" },
    { id: "cand-c1", text: "DEMO candidate C1 text…", cluster: "gamma", score: 0.52, branch: "branch-c" },
  ],
  clusters: [
    { name: "alpha", members: ["cand-a1", "cand-a2"], centroid_score: 0.845 },
    { name: "beta", members: ["cand-b1", "cand-b2"], centroid_score: 0.715 },
    { name: "gamma", members: ["cand-c1"], centroid_score: 0.52 },
  ],
  provenance_tree: [
    { branch: "branch-a", parent: null, station: "S04" },
    { branch: "branch-b", parent: "branch-a", station: "S09" },
    { branch: "branch-c", parent: "branch-a", station: "S09" },
  ],
});

export const demoQuarantine = (): QuarantineRecord[] => [
  {
    id: "q-demo-001", request_id: "req-demo-0001", reason_code: "SPECULATIVE_CLAIM",
    risk_class: "medium", station_id: "S11", status: "quarantined",
    created_at: DEMO_TS, history: [{ at: DEMO_TS, event: "DEMO: quarantined by S11" }],
  },
  {
    id: "q-demo-002", request_id: "req-demo-0002", reason_code: "PROMPT_INJECTION_PATTERN",
    risk_class: "high", station_id: "S11", status: "under_review",
    created_at: DEMO_TS, history: [{ at: DEMO_TS, event: "DEMO: flagged by Watcher" }],
  },
  {
    id: "q-demo-003", request_id: "req-demo-0003", reason_code: "HALLUCINATED_CITATION",
    risk_class: "low", station_id: "S03", status: "released",
    created_at: DEMO_TS, history: [{ at: DEMO_TS, event: "DEMO: released after review" }],
  },
];

export const demoMetrics = (): MetricsReport => ({
  latency: [
    { config: "baseline", p50_ms: 1240, p95_ms: 2380 },
    { config: "bronze-quant", p50_ms: 640, p95_ms: 1210 },
    { config: "bronze-distill", p50_ms: 410, p95_ms: 890 },
  ],
  resources: [
    { config: "baseline", cpu_ms: 8200, mem_mb: 1536 },
    { config: "bronze-quant", cpu_ms: 3900, mem_mb: 768 },
    { config: "bronze-distill", cpu_ms: 2400, mem_mb: 512 },
  ],
  quality: [
    { config: "baseline", score: 0.93 },
    { config: "bronze-quant", score: 0.9 },
    { config: "bronze-distill", score: 0.86 },
  ],
  configs: [
    { id: "baseline", description: "DEMO: unoptimized reference", params: { precision: "fp32", cache: "off" } },
    { id: "bronze-quant", description: "DEMO: quantized bronze build", params: { precision: "int8", cache: "on" } },
    { id: "bronze-distill", description: "DEMO: distilled bronze build", params: { precision: "int8", cache: "on", distill: "yes" } },
  ],
});

export const demoCompile = (source: string): VmCompileResult => ({
  ast: {
    type: "Program",
    source_preview: source.slice(0, 60),
    body: [{ type: "Halt" }],
    note: "DEMO AST — backend unreachable",
  },
  errors: [],
  symbols: ["halt"],
});

export const demoSimulate = (): VmSimulateResult => ({
  events: [
    { step: 0, kind: "init", detail: "DEMO: VM initialized" },
    { step: 1, kind: "exec", detail: "DEMO: executed HALT" },
  ],
  invariant_checks: [
    { name: "stack_balanced", passed: true, detail: "DEMO check" },
    { name: "no_unbounded_loop", passed: true, detail: "DEMO check" },
  ],
});

export const demoFormalisms = (): FormalismEntry[] => [
  {
    id: "F-001", source_equation: "DEMO: drift(t+1) = drift(t) + κ·wind(t)",
    symbols: { κ: "coupling constant", t: "breath index" },
    units: "dimensionless",
    computational_interpretation: "DEMO: S05 vector-current update",
    assumptions: ["DEMO assumption"], limitations: ["DEMO limitation"],
    implementation_ref: null, verification_status: "REVIEW_REQUIRED",
  },
  {
    id: "F-002", source_equation: "DEMO: ward = argmax_axes(coherence, safety, relevance, integrity)",
    symbols: {},
    units: "score in [0,1]",
    computational_interpretation: "DEMO: S03 dual-ward decision",
    assumptions: [], limitations: [],
    implementation_ref: "stations/s03_dual_ward", verification_status: "IMPLEMENTED_UNVERIFIED",
  },
];

const AUDIT_SUBSYSTEMS = [
  "gateway", "orchestrator", "stations", "memory", "quarantine",
  "vm", "telemetry", "verifier", "contracts", "providers",
];
const AUDIT_SEVERITIES = ["fatal", "high", "medium", "low"] as const;
const AUDIT_STATUSES = [
  "resolved_verified", "implemented_unverified", "partially_resolved",
  "scheduled", "blocked", "not_applicable",
] as const;

export const demoAudit = (): AuditResponse => {
  const records: AuditRecord[] = Array.from({ length: 78 }, (_, i) => {
    const n = i + 1;
    return {
      id: `S${String(n).padStart(3, "0")}`,
      title: `DEMO audit record ${n} — ${AUDIT_SUBSYSTEMS[i % AUDIT_SUBSYSTEMS.length]} review`,
      classification: "DEMO",
      severity: AUDIT_SEVERITIES[i % AUDIT_SEVERITIES.length],
      subsystem: AUDIT_SUBSYSTEMS[i % AUDIT_SUBSYSTEMS.length],
      description: "DEMO: placeholder record — backend /v2/audit unreachable.",
      root_cause: "DEMO",
      correction: "DEMO",
      implementation_files: [],
      verification_method: "DEMO",
      test_id: null,
      status: AUDIT_STATUSES[i % AUDIT_STATUSES.length],
      status_justification: "DEMO",
      residual_risk: "DEMO",
    };
  });
  return {
    records,
    gap: {
      from: 79,
      to: 144,
      note: "Records #79–144 were not supplied by the backend — no data to display.",
    },
    enhancements: { note: "Enhancement registry was not supplied by the backend." },
  };
};
