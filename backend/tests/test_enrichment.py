"""Metadata enrichment: what may be proposed, and what may never be.

Three properties are load-bearing and each has a test here:

* nothing is invented — a field that cannot be grounded stays unset;
* author and creation date come only from the document's own metadata;
* suggestions are drafts until a human approves them.
"""
import pytest
from sqlalchemy import select

from app.models import Artifact
from app.services.artifacts.enrichment import enrich
from app.services.artifacts.enrichment.deterministic import DeterministicEnricher

REVENUE = (
    "Quarterly revenue grew twelve percent. Revenue growth was driven by enterprise "
    "subscriptions. Enterprise customers renewed at a higher rate than last year. "
    "The subscription business now represents most of revenue.\n"
)


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def post(client, name, content, ctype="text/plain"):
    return client.post("/api/artifacts", files={"file": (name, content, ctype)})


# --- what the document asserts about itself --------------------------------

def test_document_metadata_fills_author_and_date(client, signed_in):
    from tests.fixtures import make_pdf

    content = make_pdf(
        [REVENUE],
        title="Annual Report",
        author="J. Dizon",
        subject="FY26 results",
        keywords="revenue, enterprise",
    )
    body = post(client, "report.pdf", content, "application/pdf").json()

    assert body["metadata"]["author"] == "J. Dizon"
    assert body["metadata"]["title"] == "Annual Report"
    assert body["metadata"]["description"] == "FY26 results"
    assert body["metadata"]["created_date"]
    # And each field says where it came from.
    assert body["field_methods"]["author"] == "document_metadata"
    assert body["field_methods"]["title"] == "document_metadata"
    # The document's own keywords lead the tags.
    assert body["metadata"]["tags"][:2] == ["revenue", "enterprise"]


def test_author_is_never_invented_when_the_document_has_none(client, signed_in):
    """Author is a claim about the world. Reading the text cannot establish it."""
    body = post(client, "anonymous.txt", REVENUE.encode()).json()

    assert body["metadata"]["author"] is None
    assert body["metadata"]["created_date"] is None
    assert body["field_methods"]["author"] == "not_established"
    assert body["field_methods"]["created_date"] == "not_established"


def test_a_title_the_document_does_not_assert_falls_back_to_the_filename(client, signed_in):
    body = post(client, "quarterly-notes.txt", REVENUE.encode()).json()
    assert body["metadata"]["title"] == "quarterly-notes"
    assert body["field_methods"]["title"] == "filename_stem"


# --- statistics over the document's own words ------------------------------

def test_topics_and_tags_come_from_the_document(client, signed_in):
    body = post(client, "revenue.txt", REVENUE.encode()).json()

    topics = body["metadata"]["topics"]
    assert topics, "expected topics from a document with recurring subject matter"
    # Every topic is a phrase the document actually contains.
    for topic in topics:
        assert topic.lower() in REVENUE.lower()
    assert body["field_methods"]["topics"] == "keyphrase_extraction"
    for tag in body["metadata"]["tags"]:
        assert tag.lower() in REVENUE.lower()


def test_a_document_too_short_to_judge_gets_no_topics(client, signed_in):
    """Padding a list to look thorough would be fabrication."""
    body = post(client, "tiny.txt", b"Hello there.\n").json()
    assert body["metadata"]["topics"] == []
    assert body["metadata"]["tags"] == []


def test_people_organizations_and_projects_are_never_proposed(client, signed_in):
    """Naming an entity needs recognition this engine does not have."""
    content = b"Ada Lovelace met Charles Babbage at the Analytical Engine Project.\n" * 4
    body = post(client, "entities.txt", content).json()

    assert body["metadata"]["people"] == []
    assert body["metadata"]["organizations"] == []
    assert body["metadata"]["projects"] == []


def test_language_is_detected_when_clear_and_left_unset_when_not():
    enricher = DeterministicEnricher()
    english = enricher.enrich(text=REVENUE * 2, properties={}, filename="a.txt")
    assert english.suggestions["language"] == "en"

    spanish = enricher.enrich(
        text=(
            "El conocimiento de la memoria que se guarda en el sistema para los "
            "usuarios de la red con una interfaz que no es compleja y que se usa "
            "por todos los equipos del grupo de trabajo."
        ),
        properties={},
        filename="a.txt",
    )
    assert spanish.suggestions["language"] == "es"

    # A table of numbers has no function words to go on.
    numbers = enricher.enrich(
        text="1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25",
        properties={},
        filename="a.txt",
    )
    assert "language" not in numbers.suggestions


def test_the_description_is_a_quote_not_a_summary(client, signed_in):
    body = post(client, "revenue.txt", REVENUE.encode()).json()
    assert body["field_methods"]["description"] == "extracted_opening"
    # Verbatim from the document, so it can be checked against the source.
    assert body["metadata"]["description"].startswith("Quarterly revenue grew")


# --- suggestions are drafts ------------------------------------------------

def test_suggestions_are_unconfirmed_until_the_human_approves(client, signed_in, db):
    body = post(client, "revenue.txt", REVENUE.encode()).json()
    assert body["integrity"]["human_reviewed"] is False
    assert "human_confirmed" not in body["field_methods"].values()

    client.patch(
        f"/api/artifacts/{body['id']}",
        json={
            "metadata": {**body["metadata"], "title": "FY26 Revenue"},
            "approve": True,
        },
    )
    row = db.scalars(select(Artifact)).one()
    assert row.field_methods["title"] == "human_confirmed"
    assert row.field_methods["topics"] == "human_confirmed"


def test_deterministic_enrichment_is_not_recorded_as_ai(client, signed_in):
    """`ai_enrichment` must keep meaning "a model touched this"."""
    body = post(client, "revenue.txt", REVENUE.encode()).json()

    assert body["provenance"]["ai_enrichment"] is None
    assert body["provenance"]["enrichment"]["ai_used"] is False
    assert body["provenance"]["enrichment"]["engine"] == "deterministic"
    assert body["provenance"]["enrichment"]["local"] is True


def test_enrichment_is_deterministic(client, signed_in):
    """The same document enriches the same way twice."""
    first = enrich(text=REVENUE, properties={}, filename="a.txt")
    second = enrich(text=REVENUE, properties={}, filename="a.txt")
    assert first.suggestions == second.suggestions
    assert first.methods == second.methods


# --- the local model ------------------------------------------------------

def test_a_model_may_not_propose_an_author_or_date():
    """Even if it tries, the suggestion is discarded and the attempt noted."""
    from app.services.artifacts.enrichment.llm import OllamaEnricher

    enricher = OllamaEnricher()
    enricher._ask = lambda text: {  # noqa: SLF001 - exercising the response handler
        "title": "Quarterly Revenue Review",
        "description": "A review of revenue growth.",
        "topics": ["enterprise subscriptions", "a topic the document never mentions"],
        "tags": ["revenue"],
        "author": "Someone Invented",
        "created_date": "1999-01-01",
    }

    result = enricher.enrich(text=REVENUE, properties={}, filename="a.pdf")

    assert "author" not in result.suggestions
    assert "created_date" not in result.suggestions
    assert any("author" in note for note in result.notes)
    # Ungrounded topics are dropped; grounded ones kept.
    assert result.suggestions["topics"] == ["enterprise subscriptions"]
    assert any("Dropped 1 suggested topics" in note for note in result.notes)
    assert result.methods["title"] == "ai_suggested"
    assert result.ai_used is True
    assert result.local is True


def test_a_model_cannot_overwrite_what_the_document_asserts():
    """Document metadata outranks a model, always."""
    from app.services.artifacts.enrichment.base import Enrichment

    deterministic = DeterministicEnricher().from_properties(
        properties={"title": "Annual Report", "author": "J. Dizon"}
    )
    model = Enrichment(
        suggestions={"title": "Something The Model Preferred"},
        methods={"title": "ai_suggested"},
        engine="ollama",
        ai_used=True,
    )

    merged = deterministic.merge(model)
    assert merged.suggestions["title"] == "Annual Report"
    assert merged.methods["title"] == "document_metadata"


def test_an_unreachable_model_falls_back_to_deterministic_only():
    """No fallback to anything that would send content elsewhere."""
    from app.services.artifacts.enrichment.llm import OllamaEnricher

    # A real engine pointed at a port with nothing on it.
    result = OllamaEnricher(base_url="http://127.0.0.1:1").enrich(
        text=REVENUE, properties={}, filename="a.pdf"
    )
    assert result.suggestions == {}
    assert result.ai_used is False
    assert any("could not be reached" in note for note in result.notes)


def test_tags_prefer_names_the_document_repeats():
    """Frequency alone surfaces words like "driven". Tags should name things."""
    from app.services.artifacts.enrichment.keyphrases import extract

    text = (
        "Acme Corp met with Globex about the Atlas migration. Atlas will move to "
        "Acme Corp data centres in March. Globex asked for a revised Atlas timeline, "
        "and Acme Corp agreed to send the Atlas plan. The migration covers forty "
        "database clusters and the reporting pipeline. Database performance during "
        "migration is the main risk, so the pipeline runs in parallel for two weeks. "
        "Reporting must stay available throughout the migration. Globex signs off the "
        "timeline once the database tests pass."
    )
    topics, tags = extract(text)

    # Names, in the document's own spelling, not lowercased guesses.
    assert "Globex" in tags
    # Weak verbs and connectives never reach either list.
    for junk in ("driven", "represents", "based", "across"):
        assert junk not in tags
        assert junk not in [t.lower() for t in topics]
    # Topics and tags never name the same thing twice.
    assert not ({t.lower() for t in topics} & {t.lower() for t in tags})


def test_a_word_used_once_is_never_a_tag():
    """A tag is a claim that the document is about something."""
    from app.services.artifacts.enrichment.keyphrases import extract

    text = (
        "The committee approved the drainage easement for the northern parcel. "
        "Nothing else was discussed at any length by anyone present today."
    )
    _topics, tags = extract(text)
    assert tags == []


def test_the_model_may_name_people_and_organizations_it_can_point_to():
    """Entity recognition is the one thing statistics cannot do here."""
    from app.services.artifacts.enrichment.llm import OllamaEnricher

    text = "Acme Corp met with Globex about Atlas. Ada Lovelace led the review."
    enricher = OllamaEnricher()
    enricher._ask = lambda _text: {  # noqa: SLF001 - exercising the response handler
        "people": ["Ada Lovelace", "Grace Hopper"],
        "organizations": ["Acme Corp", "Globex", "Initech"],
        "projects": ["Atlas"],
    }

    result = enricher.enrich(text=text, properties={}, filename="a.pdf")

    # Grounded entries kept, invented ones dropped — including the invented
    # person, which is the worst thing a model here could fabricate.
    assert result.suggestions["people"] == ["Ada Lovelace"]
    assert result.suggestions["organizations"] == ["Acme Corp", "Globex"]
    assert result.suggestions["projects"] == ["Atlas"]
    assert any("Dropped 1 suggested people" in note for note in result.notes)


def test_statistics_never_name_people_or_organizations(client, signed_in):
    """Telling a person from a company needs knowledge, not word counts."""
    content = b"Ada Lovelace met Charles Babbage. Ada Lovelace wrote the notes.\n" * 3
    body = post(client, "entities.txt", content).json()

    assert body["metadata"]["people"] == []
    assert body["metadata"]["organizations"] == []
    assert body["metadata"]["projects"] == []
