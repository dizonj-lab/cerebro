"""Deterministic hashing embedder.

The default provider, and the one the test suite uses. It needs no model
download, no network and no GPU, and the same text always produces the same
vector — so tests assert on real values rather than on mocks.

It is a hashing trick over word unigrams and bigrams, not a learned model:
it captures lexical overlap, not meaning. Two paraphrases with no shared
words score near zero. That is a real limitation and the reason a learned
local provider (Ollama) exists alongside it; it is not presented as
semantic search.
"""
from __future__ import annotations

import hashlib
import math
import re

_TOKEN = re.compile(r"[a-z0-9]+")

DEFAULT_DIMENSIONS = 384


class HashingEmbedder:
    name = "hashing"
    is_local = True

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        if dimensions < 16:
            raise ValueError("dimensions must be at least 16")
        self.dimensions = dimensions
        # The model identity includes the width: vectors of different widths
        # are different spaces and must not be compared.
        self.model = f"hashing-v1-{dimensions}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _features(self, text: str) -> list[str]:
        tokens = _TOKEN.findall(text.lower())
        bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        return tokens + bigrams

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for feature in self._features(text):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            # The sign comes from a different part of the digest, so colliding
            # features cancel as often as they reinforce.
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            # No usable tokens. A zero vector is honest: it matches nothing,
            # rather than matching everything equally.
            return vector
        return [v / norm for v in vector]
