"""Deterministic mock providers for dev/test. Always labeled mock=True.

- MockGrokAdapter ("Keeper"): deterministic seeded text generation.
- MockDeepSeekAdapter ("Watcher"): deterministic 4-axis safety scores derived
  from simple text heuristics (length, banned-word list, contradiction keyword
  pairs, PII patterns). NOT a real safety classifier.
"""
from __future__ import annotations

import hashlib
import random
import re
from typing import AsyncIterator

from pazuzu_contracts import ProviderAdapter, ProviderCapabilities, ProviderRequest, ProviderResponse

MOCK_NOTES = ["deterministic mock adapter for development and testing", "mock: true"]


def _seed_from(req: ProviderRequest) -> int:
    if req.seed is not None:
        return int(req.seed)
    digest = hashlib.sha256(req.prompt.encode()).hexdigest()
    return int(digest[:8], 16)


BANNED_WORDS = {
    "kill", "murder", "bomb", "weapon", "poison", "suicide", "terror",
    "hack", "exploit", "malware", "ransomware", "dox", "swat",
}

# Contradiction keyword pairs: both present within a window => contradiction signal.
CONTRADICTION_PAIRS = [
    ("always", "never"),
    ("true", "false"),
    ("yes", "no"),
    ("all", "none"),
    ("is", "is not"),
    ("can", "cannot"),
    ("will", "will not"),
    ("must", "must not"),
]

PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),  # phone-ish
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN-ish
]


def watcher_scores(text: str) -> dict[str, float]:
    """Deterministic 4-axis heuristic scores in [0,1]. Simple heuristics only:
    length, banned-word hits, contradiction keyword pairs, PII regexes, and
    repetition/structure signals. This is a development stand-in, not a
    production safety classifier."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    n = max(len(words), 1)

    banned_hits = sum(1 for w in words if w in BANNED_WORDS)
    toxicity = min(1.0, banned_hits / 3.0)

    lowered = text.lower()
    contra_hits = sum(1 for a, b in CONTRADICTION_PAIRS if a in lowered and b in lowered)
    contradiction = min(1.0, contra_hits / 2.0)

    pii_hits = sum(len(p.findall(text)) for p in PII_PATTERNS)
    pii = min(1.0, pii_hits / 2.0)

    # incoherence: repetition ratio + extreme length in either direction
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    repeat_ratio = max(counts.values()) / n if counts else 0.0
    length_penalty = 0.0
    if n < 5:
        length_penalty = 0.6
    elif n > 2000:
        length_penalty = 0.4
    incoherence = round(min(1.0, max(repeat_ratio - 0.25, 0.0) * 2.0 + length_penalty), 4)

    return {
        "toxicity": round(min(1.0, toxicity), 4),
        "contradiction": round(contradiction, 4),
        "pii": round(min(1.0, pii), 4),
        "incoherence": incoherence,
    }


def watcher_decision(scores: dict[str, float]) -> tuple[str, list[str]]:
    """Map 4-axis scores to an s03-style decision + reasons."""
    reasons: list[str] = []
    if scores["toxicity"] >= 0.85 or scores["pii"] >= 0.85:
        reasons.append("severe policy signal; routing to quarantine")
        return "quarantine", reasons
    if scores["contradiction"] >= 0.8:
        reasons.append("strong internal contradiction; rejecting")
        return "reject", reasons
    if scores["toxicity"] >= 0.4 or scores["pii"] >= 0.4 or scores["incoherence"] >= 0.7:
        reasons.append("moderate risk signal; revision required")
        return "revise", reasons
    return "approve", ["all heuristic axes within tolerance"]


_TEMPLATES = [
    "Considering the request: {topic}. A careful treatment follows.",
    "The key considerations for {topic} are scope, safety, and precision.",
    "Breaking down {topic}: first the premises, then the implications.",
    "On {topic}, the responsible answer balances completeness and caution.",
    "Analysis of {topic} suggests a structured, step-wise response.",
    "Regarding {topic}: here is the measured assessment.",
]

_FILLERS = [
    "However, each claim is checked against its premises before being stated.",
    "Therefore, ambiguities are flagged rather than papered over.",
    "For example, where evidence is thin, the response says so explicitly.",
    "Moreover, the response avoids overclaiming and notes its limits.",
    "Consequently, definitions are fixed before arguments are built on them.",
]


class MockGrokAdapter(ProviderAdapter):
    """Keeper: deterministic seeded text generation. mock=True always."""

    name = "grok"

    def __init__(self) -> None:
        self.capabilities = ProviderCapabilities(
            streaming=True,
            token_probabilities=False,
            deterministic_seed=True,
            reasoning_mode=False,
            max_context_tokens=8192,
            notes=MOCK_NOTES + ["role: keeper (candidate generation)"],
        )

    def _generate_text(self, req: ProviderRequest) -> str:
        rng = random.Random(_seed_from(req))
        topic = " ".join(req.prompt.split()[:8]) or "the request"
        parts = [rng.choice(_TEMPLATES).format(topic=topic)]
        # At least 2 connective-led fillers so the dev mock reads as
        # connected prose (the s03 coherence heuristic counts discourse
        # connectives); still fully deterministic per seed.
        n_fill = max(2, min(4, len(req.prompt) // 120))
        for _ in range(n_fill):
            parts.append(rng.choice(_FILLERS))
        text = " ".join(parts)
        words = text.split()
        budget = max(20, min(req.max_tokens // 2, 400))
        return " ".join(words[:budget])

    async def generate(self, req: ProviderRequest) -> ProviderResponse:
        text = self._generate_text(req)
        return ProviderResponse(
            text=text,
            model="mock-grok-keeper",
            provider=self.name,
            tokens_in=len(req.prompt.split()),
            tokens_out=len(text.split()),
            latency_ms=1.0,
            mock=True,
            extra={"seed": _seed_from(req)},
        )

    async def stream(self, req: ProviderRequest) -> AsyncIterator[str]:
        text = self._generate_text(req)
        words = text.split()
        for i in range(0, len(words), 5):
            yield " ".join(words[i : i + 5]) + " "


class MockDeepSeekAdapter(ProviderAdapter):
    """Watcher: deterministic 4-axis heuristic scoring. mock=True always."""

    name = "deepseek"

    def __init__(self) -> None:
        self.capabilities = ProviderCapabilities(
            streaming=False,
            token_probabilities=False,
            deterministic_seed=True,
            reasoning_mode=False,
            max_context_tokens=8192,
            notes=MOCK_NOTES + ["role: watcher (heuristic safety scoring)"],
        )

    def score(self, text: str) -> dict[str, float]:
        return watcher_scores(text)

    def decide(self, text: str) -> tuple[str, list[str]]:
        return watcher_decision(self.score(text))

    async def generate(self, req: ProviderRequest) -> ProviderResponse:
        import json as _json

        scores = self.score(req.prompt)
        decision, reasons = watcher_decision(scores)
        payload = _json.dumps({"scores": scores, "decision": decision, "reasons": reasons})
        return ProviderResponse(
            text=payload,
            model="mock-deepseek-watcher",
            provider=self.name,
            tokens_in=len(req.prompt.split()),
            tokens_out=len(payload.split()),
            latency_ms=1.0,
            mock=True,
            extra={"seed": _seed_from(req)},
        )

    async def stream(self, req: ProviderRequest) -> AsyncIterator[str]:
        resp = await self.generate(req)
        yield resp.text
