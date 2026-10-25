"""Titles: a filename or file code is never the title; the document's heading is the fallback, and a
local model's reading of the whole document may replace a heading but never a real title the
document states about itself.
"""

import pytest

from app.services.artifacts.enrichment import deterministic
from app.services.artifacts.enrichment.deterministic import first_heading
from app.services.artifacts.enrichment.llm import OllamaEnricher
from app.services.artifacts.enrichment.significance import is_placeholder_title
from tests.fixtures import make_pdf


@pytest.mark.parametrize(
    "title, filename, placeholder",
    [
        ("01-PRS-ML-DAY2A", None, True),
        ("20-PRS-SM-DAY2", "20-PRS-SM-DAY2.pdf", True),
        ("IMG_2041", None, True),
        ("lecture-notes", "lecture-notes.pdf", True),
        ("Microsoft PowerPoint - 01-PRS-ML-DAY2A.pptx", None, True),
        ("GPT-4", None, False),
        ("EXP-002", None, False),
        ("COVID-19 Response Plan", None, False),
        ("Neural Network Basics", "01-PRS-ML-DAY2A.pdf", False),
        ("Microsoft Word - Q3 Revenue", None, False),
    ],
)
def test_filenames_and_file_codes_are_not_titles(title, filename, placeholder):
    assert is_placeholder_title(title, filename) is placeholder


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Neural Network Basics\nA perceptron sums its inputs.", "Neural Network Basics"),
        (
            "01-PRS-ML-DAY2A\nPattern Recognition Using Machine Learning\nDay two.",
            "Pattern Recognition Using Machine Learning",
        ),
        (
            "© 2026 National University of Singapore\nDeep Learning Systems\nmore",
            "Deep Learning Systems",
        ),
        ("Page 3\nhttps://example.com\nRecurrent Neural Networks", "Recurrent Neural Networks"),
        ("Quarterly revenue grew twelve percent. Revenue growth was strong.", None),
        ("CEREBRO is a Digital Knowledge Twin.", None),
    ],
)
def test_the_first_heading_is_the_opening_title_shaped_line(text, expected):
    assert first_heading(text, "01-PRS-ML-DAY2A.pdf") == expected


def test_a_file_code_in_document_metadata_does_not_outrank_the_heading():
    e = deterministic.DeterministicEnricher().enrich(
        text="Neural Network Basics\nA perceptron sums weighted inputs and applies an activation.",
        properties={"title": "01-PRS-ML-DAY2A"},
        filename="01-PRS-ML-DAY2A.pdf",
    )
    assert e.suggestions["title"] == "Neural Network Basics"
    assert e.methods["title"] == "first_heading"


def test_a_real_title_in_document_metadata_still_wins():
    e = deterministic.DeterministicEnricher().enrich(
        text="Agenda\nA perceptron sums weighted inputs.",
        properties={"title": "Introduction to Pattern Recognition"},
        filename="01-PRS-ML-DAY1A.pdf",
    )
    assert e.suggestions["title"] == "Introduction to Pattern Recognition"
    assert e.methods["title"] == "document_metadata"


def test_a_model_title_that_is_a_file_code_is_set_aside():
    enricher = OllamaEnricher()
    enricher._ask = lambda text: {"title": "01-PRS-ML-DAY2A"}  # noqa: SLF001
    result = enricher.enrich(text="Neural networks.", properties={}, filename="01-PRS-ML-DAY2A.pdf")
    assert "title" not in result.suggestions
    assert any("Set aside the suggested title" in n for n in result.notes)

    enricher._ask = lambda text: {"title": "Foundations of Neural Networks"}  # noqa: SLF001
    result = enricher.enrich(text="Neural networks.", properties={}, filename="01-PRS-ML-DAY2A.pdf")
    assert result.suggestions["title"] == "Foundations of Neural Networks"
    assert result.methods["title"] == "ai_suggested"


# ---- through upload


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def test_an_upload_named_by_code_is_titled_by_its_heading(client, signed_in):
    pdf = make_pdf(
        ["Neural Network Basics\nA perceptron sums weighted inputs."], title="01-PRS-ML-DAY2A"
    )
    a = client.post(
        "/api/artifacts", files={"file": ("01-PRS-ML-DAY2A.pdf", pdf, "application/pdf")}
    ).json()
    assert a["metadata"]["title"] == "Neural Network Basics"
    assert a["field_methods"]["title"] == "first_heading"


def test_a_model_suggestion_replaces_a_heading_title_but_not_a_stated_one(
    client, signed_in, db, monkeypatch
):
    from app.models import Artifact
    from app.services.artifacts import enrichment, service

    fake = OllamaEnricher()
    fake._ask = lambda text: {"title": "Foundations of Neural Networks"}  # noqa: SLF001
    monkeypatch.setattr(enrichment, "_llm_engine", lambda: fake)

    headed = make_pdf(
        ["Neural Network Basics\nA perceptron sums weighted inputs."], title="01-PRS-ML-DAY2A"
    )
    stated = make_pdf(
        ["Agenda\nA perceptron sums weighted inputs."], title="Introduction to Pattern Recognition"
    )
    ids = [
        client.post("/api/artifacts", files={"file": (name, pdf, "application/pdf")}).json()["id"]
        for name, pdf in (("01-PRS-ML-DAY2A.pdf", headed), ("01-PRS-ML-DAY1A.pdf", stated))
    ]
    for artifact_id in ids:
        service.suggest_with_model(
            db, db.get(Artifact, artifact_id), ai_suggestions=True, store=True
        )
    db.commit()

    headed_row, stated_row = (db.get(Artifact, i) for i in ids)
    assert headed_row.artifact_metadata["title"] == "Foundations of Neural Networks"
    assert headed_row.field_methods["title"] == "ai_suggested"
    assert stated_row.artifact_metadata["title"] == "Introduction to Pattern Recognition"
    assert stated_row.field_methods["title"] == "document_metadata"
