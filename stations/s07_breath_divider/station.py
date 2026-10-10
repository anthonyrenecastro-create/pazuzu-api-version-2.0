"""S07 Breath Divider — sentence/clause segmentation for speech.

Contract
--------
Splits text into sentences (regex on terminal punctuation) and clauses
(configurable separators, default ``, ; : — –``). Estimates syllables
per segment with a vowel-group heuristic — labeled ESTIMATE, not a
phonetic count. Classifies the pause after each segment:
comma/clause → "micro" (100 ms), sentence end → "medium" (400 ms),
paragraph break → "long" (800 ms). Generates SSML (``<speak>`` with
``<break time="…"/>`` tags, XML-escaped text). Streaming-safe chunking:
SSML is split into chunks of at most ``max_chunk_chars`` (default 4000)
only at word boundaries — a word is never split.

Assumptions
-----------
- Parameters: ``text`` (default ctx.prompt), ``clause_separators``
  (default [",", ";", ":", "—", "–"]), ``max_chunk_chars`` (4000),
  ``include_clauses`` (default True).
- English-oriented heuristics throughout.

Known limitations
-----------------
- Sentence regex misfires on abbreviations ("Dr.", "e.g.") and decimals.
- Syllable estimation is approximate (±1 common); it is a heuristic,
  not a pronunciation model.
- SSML uses only ``<break>``; no prosody/emphasis modeling.
"""
from __future__ import annotations

import re
import time
from xml.sax.saxutils import escape

from pazuzu_contracts import (
    ExecutionContext,
    Station,
    StationManifest,
    StationOutput,
    StationStatus,
)

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_VOWEL_GROUP = re.compile(r"[aeiouy]+", re.IGNORECASE)

PAUSE_MS = {"micro": 100, "short": 150, "medium": 400, "long": 800}


def estimate_syllables(word: str) -> int:
    """Vowel-group heuristic. ESTIMATE — not a phonetic count."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    count = len(_VOWEL_GROUP.findall(w))
    if w.endswith("e") and count > 1:  # silent-e adjustment
        count -= 1
    return max(1, count)


class S07BreathDivider(Station):
    """Sentence/clause segmentation with syllable estimates and SSML."""

    manifest = StationManifest(
        id="s07",
        name="Breath Divider",
        version="2.0.0",
        critical_path=False,
        description="Regex sentence/clause segmentation, vowel-group "
                    "syllable estimates, pause classification, SSML with "
                    "streaming-safe word-boundary chunking.",
    )

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        params = ctx.parameters or {}
        text = str(params.get("text", ctx.prompt or ""))
        separators: list[str] = params.get("clause_separators", [",", ";", ":", "—", "–"])
        max_chunk = max(256, int(params.get("max_chunk_chars", 4000)))
        include_clauses = bool(params.get("include_clauses", True))

        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        segments: list[dict] = []
        for p_idx, para in enumerate(paragraphs or [""]):
            sentences = [s.strip() for s in _SENT_SPLIT.split(para.strip()) if s.strip()]
            for s_idx, sent in enumerate(sentences):
                is_last_para = p_idx == len(paragraphs) - 1
                is_last_sent = s_idx == len(sentences) - 1
                pause = "long" if (is_last_sent and not is_last_para) else "medium"
                pieces = [sent]
                if include_clauses:
                    pat = "|".join(re.escape(sep) for sep in separators)
                    pieces = [c.strip() for c in re.split(pat, sent) if c.strip()]
                for c_idx, piece in enumerate(pieces):
                    sub_pause = "micro" if c_idx < len(pieces) - 1 else pause
                    words = piece.split()
                    segments.append({
                        "text": piece,
                        "words": len(words),
                        "syllables_estimate": sum(estimate_syllables(w) for w in words),
                        "pause_after": sub_pause,
                        "pause_ms": PAUSE_MS[sub_pause],
                        "sentence_index": s_idx,
                        "paragraph_index": p_idx,
                    })

        # SSML generation.
        ssml_parts = ["<speak>"]
        for seg in segments:
            ssml_parts.append(escape(seg["text"]))
            ssml_parts.append(f'<break time="{seg["pause_ms"]}ms"/>')
        ssml_parts.append("</speak>")
        ssml = "".join(ssml_parts)

        # Streaming-safe chunking: split only at word boundaries.
        chunks: list[str] = []
        words = ssml.split(" ")
        current: list[str] = []
        current_len = 0
        for w in words:
            add = len(w) + (1 if current else 0)
            if current and current_len + add > max_chunk:
                chunks.append(" ".join(current))
                current, current_len = [], 0
            current.append(w)
            current_len += len(w) + (1 if len(current) > 1 else 0)
        if current:
            chunks.append(" ".join(current))

        data = {
            "segments": segments,
            "ssml": ssml,
            "ssml_chunks": chunks,
            "n_segments": len(segments),
            "total_syllables_estimate": sum(s["syllables_estimate"] for s in segments),
            "total_pause_ms": sum(s["pause_ms"] for s in segments),
            "estimate_disclaimer": (
                "Syllable counts are vowel-group ESTIMATES, not phonetic "
                "measurements; sentence splitting is regex-based and "
                "misfires on abbreviations."),
        }
        warnings = []
        if not segments:
            warnings.append("no segments produced from empty text")
        return self.output(
            ctx, data, warnings=warnings,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            tokens_in=len(text.split()),
        )
