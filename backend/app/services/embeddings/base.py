"""Embedding provider contract.

A provider turns text into a vector. Which provider ran is recorded with
every vector, because vectors from different providers or models are not
comparable: a cosine similarity between two different embedding spaces is a
number with no meaning. The search path filters on provider, model and
dimensions for that reason.

Providers declare whether they are local. Nothing here may send content to a
cloud service, and a failing local provider must never be silently replaced
by one that would.
"""
from __future__ import annotations

from typing import Protocol


class EmbeddingFailed(RuntimeError):
    """The provider could not produce vectors.

    Raised rather than falling back. A fallback would either change the
    vector space without saying so, or send content somewhere the user did
    not choose.
    """


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int
    # False would mean content leaves the CEREBRO environment. No such
    # provider exists yet, and adding one requires explicit user consent.
    is_local: bool

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Vectors for each text, in order, L2-normalised.

        Normalising on write makes cosine similarity a plain dot product at
        search time.
        """
        ...
