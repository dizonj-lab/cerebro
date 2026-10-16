"""Deterministic extraction and chunking."""
import pytest

from app.services.artifacts.chunking import chunk_blocks
from app.services.artifacts.extraction import (
    SUPPORTED_EXTENSIONS,
    ExtractionFailed,
    adapter_for,
    extract,
)
from tests.fixtures import make_docx, make_pdf, make_pptx


def test_supported_extensions_cover_p0_and_p1():
    for ext in (".pdf", ".docx", ".pptx", ".txt", ".md"):
        assert ext in SUPPORTED_EXTENSIONS
        assert adapter_for(f"a{ext}") is not None


def test_unknown_type_is_refused_by_name():
    assert adapter_for("a.xyz") is None
    with pytest.raises(ExtractionFailed, match="No extractor"):
        extract(b"data", filename="a.xyz")


# --- PDF (P0) --------------------------------------------------------------

def test_pdf_extraction_preserves_page_numbers():
    content = make_pdf([
        "Page one discusses knowledge provenance.",
        "Page two discusses assisted recollection.",
    ])
    result = extract(content, filename="paper.pdf")

    assert result.structure["pages"] == 2
    assert result.as_dict()["ai_used"] is False
    pages = {b.location.page for b in result.blocks}
    assert pages == {1, 2}
    assert "provenance" in result.text
    assert "recollection" in result.text
    # Each page's text is attributed to that page, not merged.
    page_two = " ".join(b.text for b in result.blocks if b.location.page == 2)
    assert "recollection" in page_two
    assert "provenance" not in page_two


def test_scanned_pdf_is_reported_not_silently_empty():
    """A PDF with no text layer must fail loudly, not produce an empty artifact."""
    empty = make_pdf([""])
    with pytest.raises(ExtractionFailed, match="scanned"):
        extract(empty, filename="scan.pdf")


def test_corrupt_pdf_is_refused():
    with pytest.raises(ExtractionFailed):
        extract(b"%PDF-1.4 this is not really a pdf", filename="broken.pdf")


# --- DOCX / PPTX (P1) ------------------------------------------------------

def test_docx_preserves_headings_sections_and_tables():
    content = make_docx(
        title="Knowledge Model",
        paragraphs=["Artifacts carry provenance.", "Fragments reference source locations."],
        table=[["Field", "Method"], ["title", "filename_stem"]],
    )
    result = extract(content, filename="model.docx")

    kinds = {b.kind for b in result.blocks}
    assert "heading" in kinds and "table" in kinds
    # Paragraphs inherit the heading above them as their section.
    body = [b for b in result.blocks if b.kind == "paragraph"]
    assert all(b.location.section == "Knowledge Model" for b in body)
    table = next(b for b in result.blocks if b.kind == "table")
    assert "filename_stem" in table.text


def test_pptx_preserves_slides_and_speaker_notes():
    content = make_pptx([
        ("Opening", "Why provenance matters", "Spend two minutes on the audit story."),
        ("Architecture", "Artifacts to fragments", None),
    ])
    result = extract(content, filename="deck.pptx")

    assert result.structure["slides"] == 2
    assert result.structure["slides_with_notes"] == 1
    notes = [b for b in result.blocks if b.kind == "notes"]
    assert len(notes) == 1
    assert notes[0].location.slide == 1
    assert "audit story" in notes[0].text
    # Slide titles become the section for their slide's blocks.
    assert any(b.location.section == "Architecture" for b in result.blocks)


def test_corrupt_office_file_is_refused():
    with pytest.raises(ExtractionFailed):
        extract(b"PK\x03\x04not-a-real-docx", filename="broken.docx")


# --- chunking --------------------------------------------------------------

def test_chunks_never_cross_a_page_boundary():
    content = make_pdf([f"Page one. {'Alpha sentence here. ' * 40}",
                        f"Page two. {'Beta sentence here. ' * 40}"])
    chunks = chunk_blocks(extract(content, filename="long.pdf").blocks, chunk_chars=300)

    assert len(chunks) > 2
    for chunk in chunks:
        page = chunk.source_location.get("page")
        assert page in (1, 2)
        # A chunk's text belongs to exactly one page.
        assert not ("Alpha" in chunk.content and "Beta" in chunk.content)


def test_chunks_are_contiguous_hashed_and_located():
    result = extract(("# Head\n\n" + "Sentence about recall. " * 80).encode(), filename="a.md")
    chunks = chunk_blocks(result.blocks, chunk_chars=400, overlap_chars=80)

    assert [c.ordinal for c in chunks] == list(range(1, len(chunks) + 1))
    assert all(len(c.content_sha256) == 64 for c in chunks)
    assert all("char_start" in c.source_location for c in chunks)


def test_overlap_carries_context_across_the_seam():
    # Distinct sentences: a text of one repeated sentence produces identical
    # chunks, which are deduplicated, so it would measure that instead.
    body = " ".join(f"Sentence number {i} carries its own words." for i in range(60))
    result = extract(body.encode(), filename="a.txt")
    with_overlap = chunk_blocks(result.blocks, chunk_chars=300, overlap_chars=100)
    without = chunk_blocks(result.blocks, chunk_chars=300, overlap_chars=0)
    assert len(with_overlap) > len(without)


def test_chunking_is_deterministic():
    content = make_pdf(["Determinism matters. " * 30])
    blocks = extract(content, filename="d.pdf").blocks
    first = chunk_blocks(blocks, chunk_chars=250)
    second = chunk_blocks(blocks, chunk_chars=250)
    assert [c.content_sha256 for c in first] == [c.content_sha256 for c in second]


@pytest.mark.parametrize("kwargs", [
    {"chunk_chars": 10},
    {"chunk_chars": 200, "overlap_chars": 200},
])
def test_invalid_chunk_settings_rejected(kwargs):
    with pytest.raises(ValueError):
        chunk_blocks([], **kwargs)
