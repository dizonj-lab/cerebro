"""Estimating tokens without shipping a tokeniser.

An embedding model's context is small and it is counted in tokens, while
everything CEREBRO can measure exactly is counted in characters. The old
bridge between the two was "four characters per token", the English prose
average, and it is where PDF ingestion broke: a slide deck is not prose. It
is dense with symbols, URLs, code, short fragments and capitalised headings,
all of which wordpiece splits far more finely — closer to two and a half
characters per token. A 2000-character chunk sized for 500 tokens of prose
arrived at the daemon as roughly 700 tokens of slide, and
mxbai-embed-large's context is 512.

So the estimate here is deliberately **pessimistic**. Over-estimating costs
a slightly smaller chunk; under-estimating costs the whole registration,
which is the failure this module exists to prevent. It takes the larger of
two readings — one from words, one from characters — because a document can
be dense in either direction, and neither alone catches both.

A real tokeniser would be exact, and would mean shipping one per model and
still being wrong for the next one. The guard against the estimate being
wrong is not a better estimate: it is that nothing is ever sent without
being checked against the limit first.
"""
from __future__ import annotations

import math

# Characters per token for text that tokenises badly. Measured against the
# failing case rather than chosen: a 1282-character slide chunk that the
# daemon rejected as over 512 tokens.
DENSE_CHARS_PER_TOKEN = 2.5
# Wordpiece splits long and rare words into several pieces, and punctuation
# into its own. More than one token per word is the common case.
TOKENS_PER_WORD = 1.4

# What each embedding model will accept, by family. A model absent here is
# assumed to be the smallest common size rather than the largest: guessing
# high is the mistake that produces the error this file prevents.
CONTEXT_TOKENS = {
    "mxbai-embed-large": 512,
    "nomic-embed-text": 8192,
    "bge-m3": 8192,
    "all-minilm": 256,
}
DEFAULT_CONTEXT_TOKENS = 512


def estimate(text: str) -> int:
    """A pessimistic token count for this text."""
    if not text:
        return 0
    words = len(text.split())
    return max(math.ceil(words * TOKENS_PER_WORD), math.ceil(len(text) / DENSE_CHARS_PER_TOKEN))


def context_for(model: str, limit: int | None = None) -> int:
    """The token limit for a model name, tag and all.

    `limit` is the owner's stated limit for this model and wins when given.
    It can only ever be lower than what the model publishes — the settings
    layer refuses a higher one for a model in this table — so a stated limit
    narrows the budget and never widens it past what the daemon accepts. A
    model missing from the table falls back to the smallest common size,
    because guessing high is the mistake that produces the error this module
    exists to prevent.
    """
    if limit:
        return limit
    family = (model or "").split(":", 1)[0].strip().lower()
    return CONTEXT_TOKENS.get(family, DEFAULT_CONTEXT_TOKENS)


def fits(text: str, model: str, limit: int | None = None) -> bool:
    return estimate(text) <= context_for(model, limit)
