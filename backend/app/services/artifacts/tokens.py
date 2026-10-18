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

# A wordpiece model wraps every input in [CLS] … [SEP]. Those are tokens the
# daemon counts and the text does not contain, so a chunk measured at exactly
# the context length arrives two tokens over it. This is the gap the previous
# fix left open: the guard allowed an estimate equal to the limit, which for
# mxbai-embed-large is a 1280-character chunk — passing every check and then
# refused by the daemon as "input length exceeds the context length".
SPECIAL_TOKENS = 2
# Further headroom, because the estimate is an estimate. Two characters of
# difference decided whether the old boundary case was caught, which is far
# too fine a margin to rest a registration on.
SAFETY_TOKENS = 8
# Never leave less than this to put text in, however small the context.
MIN_PAYLOAD_TOKENS = 16


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


def payload_limit(model: str, limit: int | None = None) -> int:
    """The most *text* that may be sent, as opposed to the model's context.

    The context has to hold the special tokens as well as the text, so the
    text's share is smaller than the context — always, for every model and
    every caller. Measuring against the context instead of against this is
    what let a chunk two tokens too long through.
    """
    return max(context_for(model, limit) - SPECIAL_TOKENS - SAFETY_TOKENS, MIN_PAYLOAD_TOKENS)


def fits(text: str, model: str, limit: int | None = None) -> bool:
    return estimate(text) <= payload_limit(model, limit)


def split_to_fit(text: str, limit: int) -> list[str]:
    """`text` as one piece, or several that each fit inside `limit`.

    The last net before a request goes out, so it splits on whitespace and
    nothing cleverer: by the time text arrives here the chunker has already
    failed to size it, and the only thing that matters is that no character
    is lost. Fragment boundaries are the chunker's business and it splits on
    sentences for exactly that reason; these pieces are recombined into one
    vector, so where they divide changes nothing a search can see.

    Never truncates and never discards: every character of the input appears
    in exactly one piece. A single word longer than the limit is returned
    whole rather than cut, because cutting a word is losing content — the
    guard will then refuse it and say so, which is the honest outcome.
    """
    if estimate(text) <= limit:
        return [text]

    pieces: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and estimate(candidate) > limit:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces or [text]
