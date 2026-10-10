"""S11 Pattern Quarantine — quarantine records, sanitization, dead letters.

Contract
--------
Creates ``QuarantineRecord`` entries (from ``pazuzu_contracts``) with a
reason code and risk classification:

- Reason codes: SAFETY_CRITICAL, PII_LEAK, POLICY_VIOLATION,
  CONTRADICTION_SEVERE, OPERATOR_FLAG.
- Risk classes: low / medium / high / critical (critical reserved for
  SAFETY_CRITICAL or explicit override).

Sanitization pipeline (documented: sanitization ≠ factual validation):
redacting PII and masking dangerous patterns makes a payload *safer to
handle* — it does NOT make its claims true, and sanitized text must
never be presented as verified.

Release requires an admin review flag: ``ctx.parameters["release_request"]``
= {record_id, admin_reviewed: true, reviewer}. Without it the record
stays quarantined.

The dead-letter queue is SEPARATE from active quarantine: payloads that
fail quarantine intake (or are explicitly routed with reason
DEAD_LETTER) go to an isolated list that is never scanned by release
flows.

Assumptions
-----------
- Parameters: ``quarantine_request`` {reason_code, risk_class, payload,
  payload_ref}, ``release_request`` {record_id, admin_reviewed, reviewer},
  ``dead_letter`` {payload, reason}.
- Stores are process-local (instance lists); durable deployments must
  persist them.

Known limitations
-----------------
- PII redaction uses the same regexes as S03 (false +/- possible).
- Pattern masking is lexical; obfuscated or encoded payloads pass through.
- No real access control on release beyond the admin_reviewed flag —
  the orchestrator must authenticate the reviewer.
"""
from __future__ import annotations

import hashlib
import re
import time

from pazuzu_contracts import (
    ExecutionContext,
    QuarantineRecord,
    Station,
    StationManifest,
    StationOutput,
    StationStatus,
)

REASON_CODES = {"SAFETY_CRITICAL", "PII_LEAK", "POLICY_VIOLATION",
                "CONTRADICTION_SEVERE", "OPERATOR_FLAG", "DEAD_LETTER"}
RISK_CLASSES = {"low", "medium", "high", "critical"}

PII_PATTERNS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d[ -]?){13,16}\b",
    "api_key": r"\b(sk-[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{16}|xox[bap]-[A-Za-z0-9-]{8,}|ghp_[A-Za-z0-9]{20,})\b",
}
MASK_PATTERNS = [
    r"(?i)\bhow to (build|make|construct)\b.{0,40}\b(bomb|explosive|bioweapon|chemical weapon)\b",
    r"(?i)\b(produce|manufacture|synthesize)\b.{0,40}\b(meth(amphetamine)?|fentanyl|sarin|ricin|anthrax)\b",
]


def sanitize(payload: str) -> tuple[str, dict]:
    """Sanitization pipeline: PII redaction + pattern masking.

    Documented: sanitization ≠ factual validation. Output is safer to
    handle, not verified as true.
    """
    redactions: dict[str, int] = {}
    out = payload
    for name, pat in PII_PATTERNS.items():
        out, n = re.subn(pat, f"[REDACTED:{name.upper()}]", out)
        if n:
            redactions[name] = n
    masks = 0
    for pat in MASK_PATTERNS:
        out, n = re.subn(pat, "[MASKED:SAFETY]", out)
        masks += n
    return out, {"pii_redactions": redactions, "patterns_masked": masks}


class S11PatternQuarantine(Station):
    """Quarantine records with sanitization and a separate dead-letter queue."""

    manifest = StationManifest(
        id="s11",
        name="Pattern Quarantine",
        version="2.0.0",
        critical_path=True,
        description="QuarantineRecord creation with reason codes + risk "
                    "classes, PII-redaction/pattern-masking sanitization, "
                    "admin-gated release, isolated dead-letter queue.",
    )

    def __init__(self) -> None:
        # Process-local stores; persist in production.
        self._quarantine: list[QuarantineRecord] = []
        self._dead_letter: list[dict] = []

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        params = ctx.parameters or {}
        result: dict = {}
        status = StationStatus.OK
        warnings: list[str] = []

        # Dead-letter intake: separate queue, never scanned by release.
        dl = params.get("dead_letter")
        if dl:
            entry = {
                "payload": str(dl.get("payload", ""))[:2000],
                "reason": str(dl.get("reason", "unspecified")),
                "request_id": ctx.request_id,
            }
            self._dead_letter.append(entry)
            result["dead_lettered"] = {"reason": entry["reason"],
                                       "queue_size": len(self._dead_letter)}
            warnings.append("payload routed to dead-letter queue (isolated from quarantine)")

        # Quarantine intake.
        qr = params.get("quarantine_request")
        if qr:
            reason = str(qr.get("reason_code", "OPERATOR_FLAG"))
            if reason not in REASON_CODES:
                self._dead_letter.append({
                    "payload": str(qr.get("payload", ""))[:2000],
                    "reason": f"invalid reason_code '{reason}'",
                    "request_id": ctx.request_id})
                status = StationStatus.FAILED
                result["error"] = f"invalid reason_code '{reason}'; routed to dead-letter"
            else:
                risk = str(qr.get("risk_class", "medium"))
                if risk not in RISK_CLASSES:
                    risk = "medium"
                if reason == "SAFETY_CRITICAL":
                    risk = "critical"
                payload = str(qr.get("payload", ""))
                payload_ref = qr.get("payload_ref") or hashlib.sha256(
                    payload.encode()).hexdigest()[:16]
                sanitized, san_report = sanitize(payload)
                rec = QuarantineRecord(
                    request_id=ctx.request_id,
                    reason_code=reason,
                    risk_class=risk,  # type: ignore[arg-type]
                    payload_ref=payload_ref,
                    station_id=self.manifest.id,
                    history=[{"event": "quarantined", "sanitization": san_report}],
                )
                self._quarantine.append(rec)
                result["quarantined"] = rec.model_dump(mode="json")
                result["sanitized_payload"] = sanitized
                result["sanitization_report"] = san_report
                result["sanitization_disclaimer"] = (
                    "Sanitization (PII redaction + pattern masking) makes the "
                    "payload safer to HANDLE; it does NOT validate any factual "
                    "claims. Sanitized text is not verified text.")

        # Release: requires admin review flag.
        rel = params.get("release_request")
        if rel:
            rid = rel.get("record_id")
            rec = next((r for r in self._quarantine if r.id == rid), None)
            if rec is None:
                status = StationStatus.FAILED
                result["release_error"] = f"record {rid} not found in active quarantine"
            elif not rel.get("admin_reviewed"):
                result["release"] = {"record_id": rid, "released": False,
                                     "reason": "admin review flag required"}
                warnings.append("release blocked: admin_reviewed flag not set")
            else:
                object.__setattr__(rec, "status", "released")
                object.__setattr__(rec, "reviewed_by", str(rel.get("reviewer", "unknown")))
                rec.history.append({"event": "released",
                                    "reviewer": str(rel.get("reviewer", "unknown"))})
                result["release"] = {"record_id": rid, "released": True,
                                     "reviewer": str(rel.get("reviewer", "unknown"))}

        result["quarantine_size"] = len(self._quarantine)
        result["dead_letter_size"] = len(self._dead_letter)
        return self.output(
            ctx, result, status=status, warnings=warnings,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
