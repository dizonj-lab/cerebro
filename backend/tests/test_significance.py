"""The rule that decides which proposed concepts are knowledge."""
from app.services.artifacts.enrichment.significance import (
    canonical,
    filter_concepts,
    is_generic,
)


def test_a_format_or_protocol_alone_is_not_a_concept():
    """These were prominent Galaxy nodes, at the weight of real subjects."""
    for term in ("PDF", "HTTPS", "document", "Slides", "api", "Models"):
        assert is_generic(term), term


def test_the_same_word_in_a_phrase_is_kept():
    """Context is what makes a term a subject — the word is never banned."""
    for term in (
        "PDF Document Parsing Pipeline",
        "Secure API Communication",
        "Transformer-Based Language Models",
        "Retrieval-Augmented Reasoning",
    ):
        assert not is_generic(term), term


def test_a_subject_that_is_genuinely_about_formats_survives():
    """A library about file formats keeps its subject."""
    assert not is_generic("PDF extraction")
    assert not is_generic("HTTPS certificate rotation")


def test_spellings_of_one_concept_collapse_to_one():
    assert canonical("Models") == canonical("model") == "model"
    assert canonical("Technologies") == canonical("technology") == "technology"
    assert canonical("Vector-Databases!") == "vector database"


def test_the_more_specific_spelling_wins_a_duplicate():
    kept, rejected = filter_concepts(["RAG", "RAG Pipeline", "rag pipelines"])

    # "RAG" is not generic, so it stands on its own; the two pipeline
    # spellings are one concept and the fuller one is kept.
    assert "RAG Pipeline" in kept
    assert "rag pipelines" in rejected
    assert len([k for k in kept if canonical(k) == "rag pipeline"]) == 1


def test_nothing_is_invented_and_order_is_kept():
    kept, rejected = filter_concepts(["Knowledge Graph", "PDF", "Vector Search"])

    assert kept == ["Knowledge Graph", "Vector Search"]
    assert rejected == ["PDF"]
