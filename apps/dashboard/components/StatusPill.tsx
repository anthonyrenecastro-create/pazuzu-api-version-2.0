"use client";

const KIND_CLASS: Record<string, string> = {
  ok: "pill-ok",
  degraded: "pill-degraded",
  failed: "pill-failed",
  skipped: "pill-skipped",
  approve: "pill-ok",
  approved: "pill-ok",
  revise: "pill-warn",
  revised: "pill-warn",
  reject: "pill-failed",
  rejected: "pill-failed",
  quarantine: "pill-bad",
  quarantined: "pill-bad",
  under_review: "pill-warn",
  released: "pill-ok",
  destroyed: "pill-failed",
  low: "pill-info",
  medium: "pill-warn",
  high: "pill-bad",
  critical: "pill-failed",
  resolved_verified: "pill-ok",
  implemented_unverified: "pill-warn",
  partially_resolved: "pill-warn",
  scheduled: "pill-info",
  blocked: "pill-failed",
  not_applicable: "pill-muted",
  IMPLEMENTED_TESTED: "pill-ok",
  IMPLEMENTED_UNVERIFIED: "pill-warn",
  REVIEW_REQUIRED: "pill-warn",
  NOT_IMPLEMENTED: "pill-muted",
  fatal: "pill-failed",
};

export default function StatusPill({ value }: { value: string }) {
  const cls = KIND_CLASS[value] ?? "pill-muted";
  return <span className={`pill ${cls}`}>{value.replace(/_/g, " ")}</span>;
}
