"""S03 Dual Ward — THE SAFETY GATE (fail-closed heuristic audit).

Contract
--------
Audits a candidate text on four axes, each scored in [0, 1] by a
*documented heuristic* — these are NOT calibrated LLM judges and must
never be described as such:

- safety:     banned-pattern list; critical patterns (weapons, drug
              synthesis, self-harm instructions) force an immediate
              quarantine regardless of other scores.
- factuality: contradiction-pair checks (both members of a known
              contradictory pair present) penalize; hedging language
              ("might", "possibly") is treated as calibration and adds a
              small bonus.
- coherence:  sentence-connective score — fraction of sentences that
              open with or contain discourse connectives.
- policy:     PII regex sweep (email, phone, SSN, credit-card-like,
              API-key-like); any hit penalizes.

Decision rule: APPROVE iff min(axes) >= threshold (default 0.75,
configurable via ``approval_threshold``) AND no critical safety hit.
Otherwise one automatic remediation retry with tightened parameters
(PII redaction + threshold + 0.05): if the revised candidate passes it
is returned as REVISE (revised text attached); if it still fails →
REJECT; critical hit → QUARANTINE.

FAIL-CLOSED: any exception during the audit yields QUARANTINE, never
APPROVE. This station never mutates ctx.

Assumptions
-----------
- Candidate text comes from ``ctx.parameters["candidate"]``, else from
  the S04 output in ``ctx.station_outputs`` (``data["winner"]["text"]``),
  else the prompt itself.
- Parameters: ``approval_threshold`` (0.75), ``banned_patterns`` /
  ``critical_patterns`` (override lists), ``tighten_delta`` (0.05).

Known limitations
-----------------
- Pattern lists are illustrative, not exhaustive: absence of a hit is
  NOT proof of safety. Real deployments must layer a real classifier.
- Scores are uncalibrated heuristics; thresholds are policy choices,
  not statistically grounded cutoffs.
- Contradiction-pair list is small and English-only.
- PII regexes have false positives (e.g. long digit runs) and false
  negatives (obfuscated PII).
"""
from __future__ import annotations

import re
import time

from pazuzu_contracts import (
    Decision,
    ExecutionContext,
    Station,
    StationManifest,
    StationOutput,
    StationStatus,
)

# (pattern, critical) — illustrative, NOT exhaustive.
DEFAULT_CRITICAL_PATTERNS = [
    r"(?i)\bhow to (build|make|construct)\b.{0,40}\b(bomb|explosive|bioweapon|chemical weapon)\b",
    r"(?i)\b(produce|manufacture|synthesize)\b.{0,40}\b(meth(amphetamine)?|fentanyl|sarin|ricin|anthrax)\b",
    r"(?i)\bkill (myself|yourself)\b.{0,30}\b(how|method|instructions?|guide)\b",
]
DEFAULT_BANNED_PATTERNS = [
    r"(?i)\b(hack into|ddos|ransomware|phishing kit|credential stuffing)\b",
    r"(?i)\bbuy (stolen|fake) (ids?|passports?|credit cards?)\b",
]

CONTRADICTION_PAIRS = [
    ("always", "never"),
    ("is true", "is false"),
    ("definitely", "impossible"),
    ("all", "none"),
    ("everyone", "no one"),
    ("certain", "uncertain"),
]
HEDGES = ["might", "could", "possibly", "perhaps", "likely", "unlikely",
          "suggests", "appears", "may be", "tends to"]
CONNECTIVES = ["however", "therefore", "because", "although", "furthermore",
               "moreover", "in contrast", "for example", "as a result",
               "meanwhile", "nevertheless", "consequently", "first", "second",
               "finally", "in addition", "on the other hand"]

PII_PATTERNS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d[ -]?){13,16}\b",
    "api_key": r"\b(sk-[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{16}|xox[bap]-[A-Za-z0-9-]{8,}|ghp_[A-Za-z0-9]{20,})\b",
}

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text.strip()) if s.strip()]


def _audit(text: str, critical_pats: list[str], banned_pats: list[str]) -> dict:
    low = text.lower()
    sents = _sentences(text)

    # Safety axis.
    crit_hits = [p for p in critical_pats if re.search(p, text)]
    ban_hits = [p for p in banned_pats if re.search(p, text)]
    safety = 0.0 if crit_hits else max(0.0, 1.0 - 0.5 * len(ban_hits))

    # Factuality axis: contradiction pairs penalize; hedging calibrates.
    contra_hits = [pair for a, b in CONTRADICTION_PAIRS
                   for pair in [(a, b)] if a in low and b in low]
    hedge_hits = sum(low.count(h) for h in HEDGES)
    factuality = min(1.0, max(0.0, 1.0 - 0.3 * len(contra_hits) + 0.05 * min(hedge_hits, 2)))

    # Coherence axis: connective usage across sentences.
    if len(sents) <= 1:
        coherence = 0.6
    else:
        with_conn = sum(1 for s in sents
                        if any(c in s.lower() for c in CONNECTIVES))
        coherence = round(0.4 + 0.6 * (with_conn / len(sents)), 4)

    # Policy axis: PII regex sweep.
    pii_hits = {name: len(re.findall(pat, text)) for name, pat in PII_PATTERNS.items()}
    pii_total = sum(pii_hits.values())
    policy = max(0.0, 1.0 - 0.5 * pii_total)

    return {
        "safety": round(safety, 4),
        "factuality": round(factuality, 4),
        "coherence": round(coherence, 4),
        "policy": round(policy, 4),
        "critical_hits": crit_hits,
        "banned_hits": ban_hits,
        "contradiction_pairs": contra_hits,
        "hedge_hits": hedge_hits,
        "pii_hits": {k: v for k, v in pii_hits.items() if v},
    }


def _redact_pii(text: str) -> str:
    out = text
    for name, pat in PII_PATTERNS.items():
        out = re.sub(pat, f"[REDACTED:{name.upper()}]", out)
    return out


class S03DualWard(Station):
    """Fail-closed four-axis heuristic safety gate."""

    manifest = StationManifest(
        id="s03",
        name="Dual Ward",
        version="2.0.0",
        critical_path=True,
        description="Fail-closed 4-axis heuristic audit (safety/factuality/"
                    "coherence/policy) with revise-once / reject / quarantine decisions.",
    )

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        try:
            return await self._run_guarded(ctx, t0)
        except Exception as exc:  # FAIL-CLOSED: never approve on error.
            return self.output(
                ctx,
                {
                    "decision": Decision.QUARANTINE.value,
                    "reason": f"audit exception (fail-closed): {type(exc).__name__}: {exc}",
                    "axes": {},
                    "provenance_note": "quarantined by exception handler; no axes computed",
                },
                status=StationStatus.DEGRADED,
                warnings=["audit raised; fail-closed quarantine applied"],
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

    async def _run_guarded(self, ctx: ExecutionContext, t0: float) -> StationOutput:
        params = ctx.parameters or {}
        threshold = float(params.get("approval_threshold", 0.75))
        tighten = float(params.get("tighten_delta", 0.05))
        critical_pats = params.get("critical_patterns", DEFAULT_CRITICAL_PATTERNS)
        banned_pats = params.get("banned_patterns", DEFAULT_BANNED_PATTERNS)

        candidate = params.get("candidate")
        if candidate is None:
            s04 = (ctx.station_outputs or {}).get("s04")
            if s04 is not None:
                candidate = (s04.data.get("winner") or {}).get("text")
        if candidate is None:
            candidate = ctx.prompt or ""
        candidate = str(candidate)

        report = _audit(candidate, critical_pats, banned_pats)
        axes = {k: report[k] for k in ("safety", "factuality", "coherence", "policy")}
        min_axis = min(axes.values())

        warnings = [
            "scores are uncalibrated heuristics, NOT LLM-judge grades; "
            "thresholds are policy choices, not statistical cutoffs",
        ]
        revised_candidate = None

        if report["critical_hits"]:
            decision = Decision.QUARANTINE
            status = StationStatus.FAILED
            warnings.append(f"critical safety pattern(s) matched: {len(report['critical_hits'])}")
        elif min_axis >= threshold:
            decision = Decision.APPROVE
            status = StationStatus.OK
        else:
            # One retry with tightened parameters: redact PII, raise bar.
            revised_candidate = _redact_pii(candidate)
            report2 = _audit(revised_candidate, critical_pats, banned_pats)
            axes2 = {k: report2[k] for k in axes}
            if report2["critical_hits"]:
                decision = Decision.QUARANTINE
                status = StationStatus.FAILED
                axes, report = axes2, report2
                warnings.append("critical hit after remediation; quarantined")
            elif min(axes2.values()) >= threshold + tighten:
                decision = Decision.REVISE
                status = StationStatus.DEGRADED
                axes, report = axes2, report2
                warnings.append("candidate auto-revised (PII redaction); resubmit revised text")
            else:
                decision = Decision.REJECT
                status = StationStatus.DEGRADED
                axes, report = axes2, report2
                warnings.append("failed even after one remediation retry")

        data = {
            "decision": decision.value,
            "axes": axes,
            "min_axis": round(min(axes.values()), 4),
            "threshold": threshold,
            "critical_safety_hit": bool(report["critical_hits"]),
            "detail": {k: v for k, v in report.items() if k not in axes},
            "candidate_length": len(candidate),
            "heuristic_disclaimer": (
                "All axis scores are deterministic lexical heuristics. "
                "They are NOT calibrated LLM-as-judge grades and carry no "
                "statistical confidence. Absence of a pattern hit is not "
                "proof of safety."
            ),
        }
        if revised_candidate is not None:
            data["revised_candidate"] = revised_candidate
        return self.output(
            ctx, data, status=status, warnings=warnings,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            tokens_in=len(candidate.split()),
        )
