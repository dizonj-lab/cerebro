"""Structure-aware chunking.

Builds on the PoC's principle (poc/src/chunking.py): segments stay
source-addressable, and no AI is involved. Extends it to respect the block
structure extraction produced, so a chunk never silently spans a page or
slide boundary and every chunk can name where it came from.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.services.artifacts import tokens
from app.services.artifacts.extraction import Block

# Sized in characters, targeted in tokens. Characters are what the splitter
# can count exactly; tokens are what the embedding model counts.
#
# The ratio used to be four characters per token — the English prose average
# — with a 500-token target, which is 2000 characters. That broke PDF
# ingestion: a slide deck tokenises nearer two and a half characters per
# token, so those 2000 characters reached the daemon as roughly 700 tokens
# against mxbai-embed-large's 512-token context, and the whole registration
# failed. The target was also set at the limit itself, leaving no room for
# the estimate to be wrong in the direction it was wrong.
#
# 350 with 50 of overlap, measured pessimistically, leaves real headroom
# under 512. A smaller chunk costs a little retrieval context; an oversized
# one costs the document.
CHARS_PER_TOKEN = tokens.DENSE_CHARS_PER_TOKEN
TARGET_TOKENS = 350
OVERLAP_TOKENS = 50
# Nothing leaves this module above this, whatever the character budget said.
HARD_LIMIT_TOKENS = 512
DEFAULT_CHUNK_CHARS = int(TARGET_TOKENS * CHARS_PER_TOKEN)
DEFAULT_OVERLAP_CHARS = int(OVERLAP_TOKENS * CHARS_PER_TOKEN)
MIN_CHUNK_CHARS = 80

# Bumped whenever the splitting rules change, so an artifact's provenance
# says which version produced its fragments.
CHUNKER = "structure_aware_sentence_packing"
CHUNKER_VERSION = 3

# Sentence boundary: terminator followed by whitespace. Deliberately simple
# and deterministic — no model, no language detection.
_SENTENCE = re.compile(r"[^.!?]+(?:[.!?]+|$)", re.MULTILINE)


@dataclass
class Chunk:
    ordinal: int
    content: str
    content_sha256: str
    source_location: dict
    kind: str

    @property
    def token_estimate(self) -> int:
        """Characters over an average, not a tokeniser's count.

        Named an estimate because that is what it is: the real count depends
        on the model's vocabulary, and the only exact numbers CEREBRO has are
        the ones a daemon reports after the fact.
        """
        return max(1, round(len(self.content) / CHARS_PER_TOKEN))

    def as_dict(self) -> dict:
        return {
            "ordinal": self.ordinal,
            "content": self.content,
            "content_sha256": self.content_sha256,
            "source_location": self.source_location,
            "kind": self.kind,
            "token_estimate": self.token_estimate,
        }


def chunking_provenance(
    chunks: list[Chunk],
    *,
    chunk_chars: int,
    overlap_chars: int,
    target_tokens: int = TARGET_TOKENS,
    limit_tokens: int = HARD_LIMIT_TOKENS,
) -> dict:
    """What produced these fragments, recorded on the artifact.

    The budget is recorded alongside the algorithm because it is now a
    setting: "which splitter" no longer answers "why is this fragment this
    size" on its own.
    """
    return {
        "algorithm": CHUNKER,
        "version": CHUNKER_VERSION,
        "chunk_chars": chunk_chars,
        "overlap_chars": overlap_chars,
        "target_tokens": target_tokens,
        "limit_tokens": limit_tokens,
        "chunks": len(chunks),
        "token_estimate": sum(c.token_estimate for c in chunks),
        # An estimate, and labelled as one everywhere it travels.
        "token_method": f"characters/{CHARS_PER_TOKEN}",
    }


def _sentences(text: str) -> list[tuple[str, int, int]]:
    out = []
    for match in _SENTENCE.finditer(text):
        s = match.group().strip()
        if s:
            start = match.start() + (len(match.group()) - len(match.group().lstrip()))
            out.append((s, start, start + len(s)))
    return out


def chunk_blocks(
    blocks: list[Block],
    *,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int | None = None,
    limit_tokens: int = HARD_LIMIT_TOKENS,
) -> list[Chunk]:
    """Chunk within block boundaries, packing sentences up to the budget.

    A chunk never crosses a block, so its page or slide is unambiguous. Short
    blocks (a heading, a slide title) become their own chunk rather than being
    merged into unrelated neighbours.
    """
    # Overlap follows the chunk size unless it is given: 15% of the budget,
    # which is the 75-in-500-token ratio. A fixed default would exceed a
    # smaller chunk size and be rejected.
    if overlap_chars is None:
        overlap_chars = max(1, round(chunk_chars * OVERLAP_TOKENS / TARGET_TOKENS))
    if chunk_chars < MIN_CHUNK_CHARS:
        raise ValueError(f"chunk_chars must be at least {MIN_CHUNK_CHARS}")
    if overlap_chars >= chunk_chars:
        raise ValueError("overlap_chars must be smaller than chunk_chars")

    chunks: list[Chunk] = []
    seen: set[str] = set()
    for block in blocks:
        for chunk in _chunk_block(
            block, len(chunks), chunk_chars=chunk_chars, overlap_chars=overlap_chars
        ):
            # Blank chunks carry nothing and identical ones cost an embedding
            # each while adding no retrievable knowledge — a repeated slide
            # footer across 29 pages is 29 copies of the same vector.
            if not chunk.content.strip() or chunk.content_sha256 in seen:
                continue
            seen.add(chunk.content_sha256)
            # The character budget is a prediction; this is the guarantee.
            # A chunk that still estimates over the limit is split rather
            # than trimmed — trimming would drop content the document has
            # and nobody would ever know which.
            for piece in _within_token_limit(chunk.content, limit_tokens):
                piece_chunk = _make(len(chunks), piece, chunk.source_location, chunk.kind)
                if piece_chunk.content_sha256 in seen and piece is not chunk.content:
                    continue
                seen.add(piece_chunk.content_sha256)
                chunks.append(
                    Chunk(
                        ordinal=len(chunks) + 1,
                        content=piece_chunk.content,
                        content_sha256=piece_chunk.content_sha256,
                        source_location=chunk.source_location,
                        kind=chunk.kind,
                    )
                )
    return chunks


def _within_token_limit(text: str, limit: int = HARD_LIMIT_TOKENS) -> list[str]:
    """`text` as one piece, or split into pieces that each fit.

    Sentences first, because a sentence is the smallest unit that still
    reads as something; words only when a single sentence is itself too
    long, which happens with tables and unbroken URLs. Nothing is discarded
    at either level: every character of the input appears in exactly one
    piece.
    """
    if tokens.estimate(text) <= limit:
        return [text]

    pieces: list[str] = []
    current = ""
    for sentence, _start, _end in _sentences(text):
        candidate = f"{current}{sentence}"
        if current and tokens.estimate(candidate) > limit:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
        # A single sentence over the limit cannot be helped by starting a
        # new one, so it is broken on whitespace.
        while tokens.estimate(current) > limit:
            head, tail = _split_on_words(current, limit)
            if not head:
                break
            pieces.append(head)
            current = tail
    if current.strip():
        pieces.append(current)
    return [p for p in pieces if p.strip()] or [text]


def _split_on_words(text: str, limit: int) -> tuple[str, str]:
    """The longest leading run of words that fits, and the rest."""
    words = text.split(" ")
    head: list[str] = []
    for index, word in enumerate(words):
        if head and tokens.estimate(" ".join([*head, word])) > limit:
            return " ".join(head), " ".join(words[index:])
        head.append(word)
    return text, ""


def _chunk_block(
    block: Block, offset: int, *, chunk_chars: int, overlap_chars: int
) -> list[Chunk]:
    """Chunk a single block. Kept separate so nothing closes over the loop."""
    base = block.location.as_dict()
    block_start = base.get("char_start", 0)

    if len(block.text) <= chunk_chars:
        return [_make(offset + 1, block.text, base, block.kind)]

    out: list[Chunk] = []
    buffer: list[tuple[str, int, int]] = []
    length = 0

    def flush() -> None:
        if not buffer:
            return
        text = " ".join(s for s, _, _ in buffer)
        out.append(
            _make(
                offset + len(out) + 1,
                text,
                {
                    **base,
                    "char_start": block_start + buffer[0][1],
                    "char_end": block_start + buffer[-1][2],
                },
                block.kind,
            )
        )

    for sentence in _sentences(block.text):
        text, _, _ = sentence
        if length + len(text) > chunk_chars and buffer:
            flush()
            # Carry the tail forward so meaning is not cut at the seam.
            carried: list[tuple[str, int, int]] = []
            carried_len = 0
            for item in reversed(buffer):
                if carried_len + len(item[0]) > overlap_chars:
                    break
                carried.insert(0, item)
                carried_len += len(item[0])
            buffer[:] = carried
            length = carried_len
        buffer.append(sentence)
        length += len(text)

    flush()
    return out


def _make(ordinal: int, text: str, location: dict, kind: str) -> Chunk:
    return Chunk(
        ordinal=ordinal,
        content=text,
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        source_location=location,
        kind=kind,
    )
