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

from app.services.artifacts.extraction import Block

DEFAULT_CHUNK_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 80

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

    def as_dict(self) -> dict:
        return {
            "ordinal": self.ordinal,
            "content": self.content,
            "content_sha256": self.content_sha256,
            "source_location": self.source_location,
            "kind": self.kind,
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
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[Chunk]:
    """Chunk within block boundaries, packing sentences up to the budget.

    A chunk never crosses a block, so its page or slide is unambiguous. Short
    blocks (a heading, a slide title) become their own chunk rather than being
    merged into unrelated neighbours.
    """
    if chunk_chars < MIN_CHUNK_CHARS:
        raise ValueError(f"chunk_chars must be at least {MIN_CHUNK_CHARS}")
    if overlap_chars >= chunk_chars:
        raise ValueError("overlap_chars must be smaller than chunk_chars")

    chunks: list[Chunk] = []
    for block in blocks:
        chunks.extend(
            _chunk_block(block, len(chunks), chunk_chars=chunk_chars,
                         overlap_chars=overlap_chars)
        )
    return chunks


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
