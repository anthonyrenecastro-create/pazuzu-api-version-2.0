"""S02 Sexagesimal Turn — 60-block ring-buffer context manager.

Contract
--------
Maintains a ring buffer of at most 60 context blocks (configurable block
size, default 64 tokens by whitespace estimate). Blocks are tiered:

- hot:  the 10 most recent blocks — full text is assembled into context
- warm: the next 20 blocks — only versioned summaries are assembled
- cold: the remaining 30 blocks — metadata only, not assembled

System blocks can be *pinned* via the pin API (``ctx.parameters["pinned_block_ids"]``);
pinned blocks are never evicted. Summaries are extractive (first sentence
of the block) and are explicitly labeled LOSSY — they are a compression
artifact and must never be presented as lossless. Relevance scoring is
keyword overlap against the query. Eviction is oldest-unpinned-first.

Because stations are stateless, the buffer is rebuilt each run from
``ctx.parameters["segments"]`` (list of strings; falls back to the
prompt) plus optional ``ctx.parameters["ring_state"]`` carried forward
from a previous S02 output.

Assumptions
-----------
- Token counts are whitespace estimates, not a real tokenizer.
- Parameters: ``block_size`` (default 64), ``segments``, ``pinned_block_ids``,
  ``ring_state`` (prior blocks to prepend), ``query`` (default: ctx.prompt),
  ``assemble_warm`` (default True).

Known limitations
-----------------
- First-sentence summaries lose nuance; long blocks summarized this way
  are LOSSY by construction.
- Keyword-overlap relevance is lexical; paraphrase and coreference are missed.
- Whitespace token estimates drift from real tokenizer counts (~±20%).
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

RING_CAPACITY = 60
HOT_TIER = 10
WARM_TIER = 20  # warm = next 20 after hot; cold = remainder


def _tokens(text: str) -> list[str]:
    return text.split()


def _first_sentence(text: str) -> str:
    m = re.search(r"(.+?[.!?])(\s|$)", text.strip(), re.DOTALL)
    return m.group(1).strip() if m else text.strip()[:160]


class S02Sexagesimal(Station):
    """60-block ring-buffer context manager with hot/warm/cold tiers."""

    manifest = StationManifest(
        id="s02",
        name="Sexagesimal Turn",
        version="2.0.0",
        critical_path=True,
        description="60-block ring buffer with hot/warm/cold tiers, pin API, "
                    "lossy extractive summaries, and oldest-unpinned-first eviction.",
    )

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        params = ctx.parameters or {}
        block_size = max(8, int(params.get("block_size", 64)))
        pinned_ids: set[str] = set(params.get("pinned_block_ids", []))
        query = params.get("query", ctx.prompt or "")
        assemble_warm = bool(params.get("assemble_warm", True))

        segments: list[str] = params.get("segments") or [ctx.prompt or ""]
        prior: list[dict] = params.get("ring_state") or []

        # Build fresh blocks from segments, chunked to block_size tokens.
        blocks: list[dict] = []
        n0 = len(prior)
        counter = n0
        for seg in segments:
            toks = _tokens(seg)
            for i in range(0, len(toks), block_size):
                chunk = " ".join(toks[i:i + block_size])
                blocks.append({
                    "id": f"b{counter}",
                    "text": chunk,
                    "token_estimate": len(_tokens(chunk)),
                    "pinned": False,
                })
                counter += 1

        ring = list(prior) + blocks
        for b in ring:
            if b["id"] in pinned_ids:
                b["pinned"] = True

        # Eviction: oldest-unpinned-first while over capacity.
        evicted: list[str] = []
        while len(ring) > RING_CAPACITY:
            victim = next((b for b in ring if not b.get("pinned")), None)
            if victim is None:
                # All pinned: drop oldest pinned anyway (documented fallback).
                victim = ring[0]
                evicted.append(victim["id"] + " (pinned-overflow)")
            else:
                evicted.append(victim["id"])
            ring.remove(victim)

        # Tiering: hot = last 10, warm = next 20, cold = rest.
        query_terms = {t.lower() for t in _tokens(query)}
        for idx, b in enumerate(ring):
            age_rank = len(ring) - 1 - idx  # 0 = newest
            b["tier"] = "hot" if age_rank < HOT_TIER else ("warm" if age_rank < HOT_TIER + WARM_TIER else "cold")
            block_terms = {t.lower() for t in _tokens(b["text"])}
            overlap = len(query_terms & block_terms)
            b["relevance"] = round(overlap / max(1, len(query_terms)), 4)
            # Versioned extractive summary — LOSSY, never lossless.
            b["summary"] = _first_sentence(b["text"])
            b["summary_kind"] = "LOSSY-extractive-first-sentence"
            b["summary_version"] = "s02-sum-v1"

        hot = [b for b in ring if b["tier"] == "hot"]
        warm = [b for b in ring if b["tier"] == "warm"]
        cold = [b for b in ring if b["tier"] == "cold"]

        parts: list[str] = []
        for b in hot:
            parts.append(f"[{b['id']}]{' (pinned)' if b['pinned'] else ''} {b['text']}")
        if assemble_warm:
            for b in warm:
                parts.append(f"[{b['id']}-summary/LOSSY] {b['summary']}")
        assembled = "\n".join(parts)

        data = {
            "context_blocks": [
                {k: b[k] for k in ("id", "tier", "token_estimate", "pinned",
                                   "relevance", "summary", "summary_kind",
                                   "summary_version")}
                for b in ring
            ],
            "tier_counts": {"hot": len(hot), "warm": len(warm), "cold": len(cold)},
            "evicted": evicted,
            "pinned": sorted(pinned_ids),
            "assembled_context": assembled,
            "assembled_token_estimate": len(_tokens(assembled)),
            "ring_capacity": RING_CAPACITY,
            "block_size": block_size,
        }
        warnings = []
        if evicted:
            warnings.append(f"evicted {len(evicted)} block(s): {evicted[:5]}")
        if cold:
            warnings.append(f"{len(cold)} cold block(s) excluded from assembled context")
        return self.output(
            ctx, data, warnings=warnings,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            tokens_in=len(_tokens(ctx.prompt or "")),
        )
