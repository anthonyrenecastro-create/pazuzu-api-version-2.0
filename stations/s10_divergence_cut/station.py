"""S10 Divergence Cut — contradiction detection and correction proposals.

Contract
--------
Splits the input text (``ctx.parameters["text"]``, else the S04 winner,
else the prompt) into sentence-level claims and checks claim pairs for
contradiction with a *labeled heuristic*: two claims contradict when
they share at least one content word (subject overlap, stopwords
removed) AND carry opposite polarity — either via negation markers
("not", "never", "n't", …) or via an antonym pair split across the two
claims.

Uncertainty is distinguished from contradiction: claims containing
hedging language ("might", "possibly", "could", …) are labeled
``uncertain`` and are never reported as contradictions — hedging is a
calibration signal, not a logical conflict.

For each detected contradiction the station emits a correction proposal:
``hedge`` (restate the weaker claim with hedging), ``scope`` (restrict
one claim's scope so both can hold), or ``escalate`` (flag for human
review when neither is safe).

Reconciliation policy: on the same segment, an S10 contradiction verdict
SUPERSEDES S05 drift flags — S10 wins over S05. S05 measures lexical
movement; S10 adjudicates logical conflict, and logic outranks drift.

Assumptions
-----------
- English, sentence-tokenizable input; claims are sentences.
- Parameters: ``text``, ``min_overlap`` (1 shared content word),
  ``antonym_pairs`` (override list).

Known limitations
-----------------
- Heuristic only: shared-word overlap is a weak proxy for "same subject";
  false positives (equivocation) and false negatives (paraphrase) occur.
- No coreference resolution, no negation-scope parsing, no NLI model.
- Antonym list is small and context-free ("open" vs "closed" can both be
  true of different things).
"""
from __future__ import annotations

import re
import time

from pazuzu_contracts import (
    ExecutionContext,
    Station,
    StationManifest,
    StationOutput,
    StationStatus,
)

NEGATIONS = ["not", "never", "n't", "no ", "none", "cannot", "neither",
             "nor", "without", "n't"]
HEDGES = ["might", "could", "possibly", "perhaps", "likely", "maybe",
          "suggests", "appears", "uncertain", "unclear"]
STOPWORDS = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
             "being", "of", "to", "in", "on", "and", "or", "it", "this",
             "that", "these", "those", "as", "at", "by", "for", "with",
             "from", "i", "you", "we", "they", "he", "she"}
ANTONYM_PAIRS = [
    ("true", "false"), ("hot", "cold"), ("open", "closed"),
    ("safe", "dangerous"), ("legal", "illegal"), ("possible", "impossible"),
    ("increase", "decrease"), ("always", "never"), ("all", "none"),
    ("easy", "hard"), ("good", "bad"), ("allow", "forbid"),
]

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _claims(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text.strip()) if s.strip()]


def _content_words(claim: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", claim.lower())
            if w not in STOPWORDS and len(w) > 2}


def _polarity(claim: str) -> str:
    low = claim.lower()
    if any(h in low for h in HEDGES):
        return "uncertain"
    if any(n in low for n in NEGATIONS):
        return "negative"
    return "positive"


def _antonym_split(a: str, b: str) -> list[list[str]]:
    la, lb = a.lower(), b.lower()
    return [[x, y] for x, y in ANTONYM_PAIRS
            if (re.search(rf"\b{re.escape(x)}\b", la) and re.search(rf"\b{re.escape(y)}\b", lb))
            or (re.search(rf"\b{re.escape(y)}\b", la) and re.search(rf"\b{re.escape(x)}\b", lb))]


class S10DivergenceCut(Station):
    """Heuristic contradiction detection with correction proposals."""

    manifest = StationManifest(
        id="s10",
        name="Divergence Cut",
        version="2.0.0",
        critical_path=False,
        description="Claim-pair contradiction detection (negation + antonym "
                    "heuristic), uncertainty distinguished from contradiction, "
                    "correction proposals. S10 verdicts supersede S05 on the "
                    "same segment.",
    )

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        params = ctx.parameters or {}
        text = params.get("text")
        if text is None:
            s04 = (ctx.station_outputs or {}).get("s04")
            if s04 is not None:
                text = (s04.data.get("winner") or {}).get("text")
        text = str(text or ctx.prompt or "")
        min_overlap = int(params.get("min_overlap", 1))
        antonyms = params.get("antonym_pairs", ANTONYM_PAIRS)

        claims = _claims(text)
        words = [_content_words(c) for c in claims]
        pols = [_polarity(c) for c in claims]

        contradictions: list[dict] = []
        uncertain: list[int] = [i for i, p in enumerate(pols) if p == "uncertain"]
        for i in range(len(claims)):
            for j in range(i + 1, len(claims)):
                if pols[i] == "uncertain" or pols[j] == "uncertain":
                    continue  # uncertainty is not contradiction
                overlap = words[i] & words[j]
                if len(overlap) < min_overlap:
                    continue
                neg_clash = ({pols[i], pols[j]} == {"positive", "negative"})
                antonym_hits = _antonym_split(claims[i], claims[j])
                if neg_clash or antonym_hits:
                    mechanism = ("negation" if neg_clash else "antonym") + \
                                ("+antonym" if neg_clash and antonym_hits else "")
                    contradictions.append({
                        "claim_a": {"index": i, "text": claims[i]},
                        "claim_b": {"index": j, "text": claims[j]},
                        "shared_terms": sorted(overlap),
                        "mechanism": mechanism,
                        "antonym_hits": antonym_hits,
                        "correction_proposals": [
                            {"type": "hedge",
                             "suggestion": f"Restate claim {j} with hedging "
                                          f"('may', 'can') to soften the conflict."},
                            {"type": "scope",
                             "suggestion": f"Restrict the scope of claim {i} or {j} "
                                          f"(time, place, condition) so both can hold."},
                            {"type": "escalate",
                             "suggestion": "Flag for human review; do not auto-resolve."},
                        ],
                    })

        data = {
            "n_claims": len(claims),
            "contradictions": contradictions,
            "n_contradictions": len(contradictions),
            "uncertain_claims": uncertain,
            "heuristic_disclaimer": (
                "Contradiction detection is a lexical heuristic (shared "
                "content words + negation/antonym markers), NOT an NLI model. "
                "Hedged claims are labeled uncertain, never contradictory."),
            "reconciliation_policy": (
                "On the same segment, an S10 contradiction verdict SUPERSEDES "
                "S05 drift flags: S10 wins over S05 (logic outranks drift)."),
        }
        warnings = []
        if contradictions:
            warnings.append(f"{len(contradictions)} contradiction(s) detected; see correction proposals")
        if uncertain:
            warnings.append(f"{len(uncertain)} hedged/uncertain claim(s) excluded from contradiction checks")
        return self.output(
            ctx, data, warnings=warnings,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            tokens_in=len(text.split()),
        )
