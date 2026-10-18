"""Chunks that fit the model's context, measured before they are sent.

The failure these cover: "llm embedding error: the input length exceeds the
context length" from mxbai-embed-large, whose context is 512 tokens, on a
PDF whose chunks were sized at four characters per token — the English prose
average, which a slide deck is not.
"""
import pytest

from app.services.artifacts import chunking, tokens
from app.services.artifacts.extraction import Block, SourceLocation

SLIDE = (
    "Graduate Certificate in Intelligent Reasoning Systems. Cognitive Systems: "
    "Audio Cognition. https://www.nus.edu.sg/course/irs (c) 2026 NUS. "
)


def blocks_of(text: str, *, page: int = 1) -> list[Block]:
    return [Block(text=text, kind="paragraph", location=SourceLocation(page=page))]


def every_chunk_fits(chunks, model="mxbai-embed-large:latest") -> bool:
    limit = tokens.context_for(model)
    return all(tokens.estimate(c.content) <= limit for c in chunks)


# --- the estimate -----------------------------------------------------------

def test_dense_text_is_not_measured_at_prose_rates():
    """Four characters per token is what broke this."""
    dense = SLIDE * 11
    # The old reading would have called this comfortably small.
    assert len(dense) / 4 < 512
    # The pessimistic one does not.
    assert tokens.estimate(dense) > 512


def test_a_models_context_is_known_by_family_not_by_tag():
    assert tokens.context_for("mxbai-embed-large:latest") == 512
    assert tokens.context_for("nomic-embed-text") == 8192
    # An unknown model is assumed small: guessing high is the mistake that
    # produces the error this prevents.
    assert tokens.context_for("something-new") == 512


# --- chunking ---------------------------------------------------------------

def test_the_target_leaves_headroom_under_the_hard_limit():
    assert chunking.TARGET_TOKENS == 350
    assert chunking.OVERLAP_TOKENS == 50
    assert chunking.HARD_LIMIT_TOKENS == 512
    assert chunking.TARGET_TOKENS < chunking.HARD_LIMIT_TOKENS


def test_normal_prose_chunks_fit(): 
    prose = (
        "The migration completed its cutover in March. The reporting pipeline "
        "followed in April, and the team agreed the timelines. "
    ) * 40
    chunks = chunking.chunk_blocks(blocks_of(prose))

    assert chunks
    assert every_chunk_fits(chunks)


def test_slide_text_chunks_fit_where_it_used_to_overflow():
    chunks = chunking.chunk_blocks(blocks_of(SLIDE * 40))

    assert chunks
    assert every_chunk_fits(chunks)


def test_an_oversized_sentence_is_split_not_truncated():
    """A table or an unbroken URL run is one sentence and far too long."""
    # Distinct words throughout: identical chunks are deduplicated by
    # design — a slide footer repeated across 29 pages is one vector, not 29
    # — and repeated filler would be measuring that instead of splitting.
    one_sentence = " ".join(f"token{n}" for n in range(1500))  # no terminator
    chunks = chunking.chunk_blocks(blocks_of(one_sentence))

    assert len(chunks) > 1
    assert every_chunk_fits(chunks)
    # Every word survives somewhere: split, never trimmed.
    rebuilt = " ".join(c.content for c in chunks).split()
    assert {f"token{n}" for n in range(1500)} <= set(rebuilt)


def test_special_characters_do_not_break_chunking():
    odd = "Σ ∑ → ⟶ «quoted» — em-dash … ellipsis 日本語 emoji 🙂 https://x.y/z?a=1&b=2 " * 30
    chunks = chunking.chunk_blocks(blocks_of(odd))

    assert chunks
    assert every_chunk_fits(chunks)
    assert all(c.content.strip() for c in chunks)


def test_a_multi_page_document_keeps_each_chunk_on_one_page():
    # Each page says something different, or the deduplication that exists
    # to collapse repeated footers would collapse the pages themselves.
    pages = [
        Block(
            text=f"Page {page} of the deck. " + SLIDE.replace("Audio", f"Topic{page}") * 12,
            kind="paragraph",
            location=SourceLocation(page=page),
        )
        for page in range(1, 6)
    ]

    chunks = chunking.chunk_blocks(pages)

    assert every_chunk_fits(chunks)
    # Provenance survives the extra splitting.
    assert {c.source_location["page"] for c in chunks} == {1, 2, 3, 4, 5}
    assert all(c.source_location for c in chunks)


def test_ordinals_stay_contiguous_after_a_split():
    chunks = chunking.chunk_blocks(blocks_of(SLIDE * 40))

    assert [c.ordinal for c in chunks] == list(range(1, len(chunks) + 1))


# --- the guard before the daemon -------------------------------------------

def test_an_oversized_payload_is_refused_before_it_is_sent():
    """Named here, where the fragment can still be identified."""
    from app.services.embeddings.base import EmbeddingFailed
    from app.services.embeddings.ollama import OllamaEmbedder

    embedder = OllamaEmbedder(
        base_url="http://127.0.0.1:1", model="mxbai-embed-large:latest", dimensions=1024
    )

    with pytest.raises(EmbeddingFailed) as caught:
        embedder.embed(["word " * 2000])

    assert "512-token context" in str(caught.value)
    assert "Re-register" in str(caught.value)


def test_chunks_this_pipeline_produces_pass_that_guard():
    """The two halves agree: what chunking emits is what embedding accepts."""
    from app.services.embeddings.ollama import OllamaEmbedder

    chunks = chunking.chunk_blocks(blocks_of(SLIDE * 60))
    embedder = OllamaEmbedder(
        base_url="http://127.0.0.1:1", model="mxbai-embed-large:latest", dimensions=1024
    )

    # Reaches the network and fails there, which means the size guard passed.
    with pytest.raises(Exception) as caught:
        embedder.embed([c.content for c in chunks])

    assert "exceed" not in str(caught.value)
