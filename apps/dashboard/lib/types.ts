/** Dashboard-side interfaces not in the shared contracts (backend-defined shapes). */

export interface KeeperWatcherStatus {
  keeper: { status: string; queue_depth: number; last_heartbeat: string };
  watcher: { status: string; queue_depth: number; last_heartbeat: string };
}

export interface GenerateResponse {
  execution: import("../../../packages/contracts/typescript").ExecutionRecord;
}

export interface WardReport {
  request_id: string;
  candidate_text: string;
  axes: { name: string; score: number; rationale: string }[];
  decision: "approve" | "revise" | "reject" | "quarantine";
  decision_detail: string;
  revisions: { at: string; decision: string; note: string }[];
}

export interface WindField {
  request_id: string;
  drift_series: { t: number; drift: number; baseline: number }[];
  contradictions: { t: number; magnitude: number; note: string }[];
  branches: { name: string; points: { t: number; drift: number }[] }[];
}

export interface MemoryCell {
  id: string;
  index: number;
  temperature: "hot" | "warm" | "cold";
  pinned: boolean;
  label: string;
  updated_at: string;
}

export interface MemoryRetrieval {
  at: string;
  cell_id: string;
  query: string;
  hit: boolean;
}

export interface SwarmReport {
  request_id: string;
  candidates: {
    id: string;
    text: string;
    cluster: string;
    score: number;
    branch: string;
  }[];
  clusters: { name: string; members: string[]; centroid_score: number }[];
  provenance_tree: { branch: string; parent: string | null; station: string }[];
}

export interface MetricsReport {
  latency: { config: string; p50_ms: number; p95_ms: number }[];
  resources: { config: string; cpu_ms: number; mem_mb: number }[];
  quality: { config: string; score: number }[];
  configs: { id: string; description: string; params: Record<string, string> }[];
}

export interface VmCompileResult {
  ast: Record<string, unknown>;
  errors: { line: number; message: string }[];
  symbols: string[];
}

export interface VmSimulateResult {
  events: { step: number; kind: string; detail: string }[];
  invariant_checks: { name: string; passed: boolean; detail: string }[];
}

export interface AuditResponse {
  records: import("../../../packages/contracts/typescript").AuditRecord[];
  gap: { from: number; to: number; note: string } | null;
  enhancements: { note: string } | null;
}
