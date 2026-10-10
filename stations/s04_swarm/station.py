"""S04 Swarm Agreement — medoid consensus over N candidates.

Contract
--------
Generates N=3 candidate responses (from ``ctx.parameters["candidates"]``
or from deterministic mock templates over the prompt), embeds each with
a *deterministic hashing vectorizer* over character 3-grams — this is a
SURROGATE similarity signal, NOT a real embedding model, and is labeled
as such in every output — then selects the medoid (the candidate with
minimum total pairwise cosine distance). Pairwise comparison is O(N²),
documented explicitly. Candidates far from the medoid (distance >
mean + std) are retained in an outlier list. Consensus confidence =
1 − dispersion, where dispersion is the mean cosine distance to the
medoid.

Minority-outlier caveat (audit #51): medoid selection suppresses
minority viewpoints by construction — a correct-but-unusual candidate
will be labeled an outlier. Outliers are retained (not deleted) so a
downstream station or human can recover them; the station never claims
the medoid is "true", only that it is central.

Assumptions
-----------
- Parameters: ``candidates`` (list[str], preferred), ``n_candidates``
  (default 3, used only for mock generation), ``vector_dim`` (default 128),
  ``outlier_std`` (default 1.0).
- Mock templates are deterministic string transforms of the prompt.

Known limitations
-----------------
- Hashing vectors capture surface n-gram overlap only; paraphrases with
  different wording score as distant. Do not confuse with semantics.
- N=3 is a tiny sample; consensus over 3 is weak evidence.
- Confidence is 1 − dispersion of a surrogate metric, uncalibrated.
"""
from __future__ import annotations

import hashlib
import math
import time

from pazuzu_contracts import (
    ExecutionContext,
    Station,
    StationManifest,
    StationOutput,
    StationStatus,
)


def hash_vector(text: str, dim: int = 128) -> list[float]:
    """Deterministic hashing vectorizer (SURROGATE — not real embeddings).

    Character 3-grams hashed into ``dim`` buckets, L2-normalized.
    Captures surface lexical overlap only.
    """
    vec = [0.0] * dim
    t = text.lower()
    for i in range(len(t) - 2):
        h = int(hashlib.md5(t[i:i + 3].encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def cosine_distance(a: list[float], b: list[float]) -> float:
    return 1.0 - sum(x * y for x, y in zip(a, b))


def _mock_candidates(prompt: str, n: int) -> list[str]:
    templates = [
        "Direct answer: {p}",
        "Structured answer: (1) restate — {p}; (2) key points follow from the request; (3) summary.",
        "Cautious answer: {p} — with the caveat that details depend on context not provided here.",
        "Concise answer: {p}",
    ]
    return [t.format(p=prompt) for t in templates[:max(1, n)]]


class S04Swarm(Station):
    """Medoid consensus over N candidates with outlier retention."""

    manifest = StationManifest(
        id="s04",
        name="Swarm Agreement",
        version="2.0.0",
        critical_path=False,
        description="N-candidate generation, surrogate hashing-vector "
                    "embedding, O(N²) medoid selection, outlier retention.",
    )

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        params = ctx.parameters or {}
        dim = int(params.get("vector_dim", 128))
        outlier_std = float(params.get("outlier_std", 1.0))

        candidates: list[str] = params.get("candidates") or _mock_candidates(
            ctx.prompt or "", int(params.get("n_candidates", 3)))
        candidates = [str(c) for c in candidates]
        n = len(candidates)
        if n == 0:
            return self.output(ctx, {"error": "no candidates"}, status=StationStatus.FAILED,
                               duration_ms=(time.perf_counter() - t0) * 1000.0)

        vecs = [hash_vector(c, dim) for c in candidates]

        # O(N²) pairwise cosine-distance matrix (documented complexity).
        dist = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                d = cosine_distance(vecs[i], vecs[j])
                dist[i][j] = dist[j][i] = d

        total = [sum(row) for row in dist]
        medoid_idx = min(range(n), key=lambda i: total[i])
        to_medoid = [dist[i][medoid_idx] for i in range(n)]
        dispersion = sum(to_medoid) / n
        mean_d = dispersion
        std_d = math.sqrt(sum((d - mean_d) ** 2 for d in to_medoid) / n) if n > 1 else 0.0

        outliers = [
            {"index": i, "text": candidates[i],
             "distance_to_medoid": round(to_medoid[i], 4)}
            for i in range(n)
            if i != medoid_idx and to_medoid[i] > mean_d + outlier_std * std_d
        ]
        confidence = round(max(0.0, 1.0 - dispersion), 4)

        data = {
            "winner": {"index": medoid_idx, "text": candidates[medoid_idx]},
            "consensus_confidence": confidence,
            "dispersion": round(dispersion, 4),
            "pairwise_distances": [[round(d, 4) for d in row] for row in dist],
            "outliers": outliers,
            "n_candidates": n,
            "complexity_note": "medoid selection is O(N²) pairwise comparisons",
            "embedding_disclaimer": (
                "Vectors are deterministic char-3-gram hashing SURROGATES, "
                "not neural embeddings; similarity reflects surface n-gram "
                "overlap only."
            ),
            "minority_outlier_caveat": (
                "Medoid selection suppresses minority viewpoints by "
                "construction (audit #51): a correct-but-unusual candidate "
                "is labeled an outlier. Outliers are retained, not deleted; "
                "the medoid is 'central', not 'true'."
            ),
        }
        warnings = []
        if outliers:
            warnings.append(f"{len(outliers)} outlier candidate(s) retained for review")
        if confidence < 0.5:
            warnings.append("low consensus confidence; candidates diverge")
        return self.output(
            ctx, data, warnings=warnings,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            tokens_in=sum(len(c.split()) for c in candidates),
        )
