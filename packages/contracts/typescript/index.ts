// PAZUZU-API v2.0 shared TypeScript contracts (mirror of Pydantic models).
export type StationStatus = "ok" | "degraded" | "failed" | "skipped";
export type Decision = "approve" | "revise" | "reject" | "quarantine";

export interface Provenance {
  request_id: string;
  correlation_id: string;
  station_id: string;
  station_version: string;
  input_hash: string;
  created_at: string;
  actor: string;
}

export interface Telemetry {
  duration_ms: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  extra: Record<string, unknown>;
}

export interface StationOutput {
  station_id: string;
  station_version: string;
  status: StationStatus;
  data: Record<string, unknown>;
  provenance: Provenance;
  telemetry: Telemetry;
  warnings: string[];
}

export interface StationManifest {
  id: string;
  name: string;
  version: string;
  critical_path: boolean;
  description: string;
}

export interface ExecutionRecord {
  request_id: string;
  correlation_id: string;
  status: string;
  plan_version: string;
  station_outputs: Record<string, StationOutput>;
  final_text: string | null;
  verification: Record<string, unknown> | null;
  created_at: string;
}

export interface QuarantineRecord {
  id: string;
  request_id: string;
  reason_code: string;
  risk_class: "low" | "medium" | "high" | "critical";
  station_id: string;
  status: "quarantined" | "under_review" | "released" | "destroyed";
  created_at: string;
  history: Record<string, unknown>[];
}

export interface StreamEvent {
  type: "candidate" | "approved" | "withheld" | "revised" | "rejected" | "completed" | "error";
  request_id: string;
  segment_index?: number;
  text?: string;
  decision?: Decision;
  detail?: Record<string, unknown>;
}

export interface FormalismEntry {
  id: string;
  source_equation: string;
  symbols: Record<string, string>;
  units: string;
  computational_interpretation: string;
  assumptions: string[];
  limitations: string[];
  implementation_ref: string | null;
  verification_status: "IMPLEMENTED_TESTED" | "IMPLEMENTED_UNVERIFIED" | "REVIEW_REQUIRED" | "NOT_IMPLEMENTED";
}

export interface AuditRecord {
  id: string;
  title: string;
  classification: string;
  severity: "fatal" | "high" | "medium" | "low";
  subsystem: string;
  description: string;
  root_cause: string;
  correction: string;
  implementation_files: string[];
  verification_method: string;
  test_id: string | null;
  status: "resolved_verified" | "implemented_unverified" | "partially_resolved" | "scheduled" | "blocked" | "not_applicable";
  status_justification: string;
  residual_risk: string;
}
