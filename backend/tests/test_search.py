"""Knowledge fragments, embeddings and search.

Runs against real PostgreSQL. The embedder is the deterministic hashing
provider, so similarity scores are real values and assertable, not mocks.
"""
import pytest
from sqlalchemy import select

from app.models import Artifact, FragmentEmbedding, KnowledgeFragment

APPROVED = {"title": "Provenance Notes", "topics": ["Provenance"]}
SAMPLE = (
    "CEREBRO preserves provenance to source artifacts.\n\n"
    "Embeddings are stored as float arrays in PostgreSQL.\n"
)


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def upload(client, name="notes.txt", content=None):
    body = (content or SAMPLE).encode("utf-8")
    return client.post(
        "/api/artifacts", files={"file": (name, body, "text/plain")}
    ).json()


def register(client, artifact_id, metadata=None):
    return client.patch(
        f"/api/artifacts/{artifact_id}",
        json={"metadata": metadata or APPROVED, "approve": True},
    )


# --- the approval gate -----------------------------------------------------

def test_an_unapproved_artifact_has_no_fragments(client, signed_in, db):
    """Nothing unapproved may enter retrieval."""
    upload(client)
    assert db.scalars(select(KnowledgeFragment)).all() == []

    # And it is unreachable by search.
    r = client.post("/api/search", json={"query": "provenance"})
    assert r.status_code == 200
    assert r.json()["matches"] == []


def test_saving_a_draft_does_not_create_fragments(client, signed_in, db):
    artifact = upload(client)
    client.patch(
        f"/api/artifacts/{artifact['id']}",
        json={"metadata": APPROVED, "approve": False},
    )
    assert db.scalars(select(KnowledgeFragment)).all() == []


def test_registration_creates_fragments_with_their_embeddings(client, signed_in, db):
    artifact = upload(client)
    assert register(client, artifact["id"]).status_code == 200

    fragments = db.scalars(select(KnowledgeFragment)).all()
    assert len(fragments) >= 1
    assert all(f.owner_id is not None for f in fragments)
    assert all(f.content_sha256 for f in fragments)

    embeddings = db.scalars(select(FragmentEmbedding)).all()
    assert len(embeddings) == len(fragments)
    one = embeddings[0]
    assert one.provider == "hashing"
    assert one.dimensions == len(one.vector) == 384
    # Vectors are normalised on write, so cosine is a dot product later.
    assert abs(sum(v * v for v in one.vector) - 1.0) < 1e-4


def test_fragments_keep_the_source_location(client, signed_in, db):
    artifact = upload(client)
    register(client, artifact["id"])

    fragment = db.scalars(select(KnowledgeFragment)).first()
    # Plain text has paragraphs and character spans, not pages. Absent keys
    # stay absent rather than being filled with a default.
    assert "char_start" in fragment.source_location
    assert "page" not in fragment.source_location


def test_fragments_from_a_pdf_carry_their_page(client, signed_in, db):
    from tests.fixtures import make_pdf

    content = make_pdf(["Provenance on page one.", "Embeddings on page two."])
    artifact = client.post(
        "/api/artifacts", files={"file": ("paged.pdf", content, "application/pdf")}
    ).json()
    register(client, artifact["id"])

    pages = {
        f.source_location.get("page") for f in db.scalars(select(KnowledgeFragment)).all()
    }
    assert pages == {1, 2}


# --- idempotency -----------------------------------------------------------

def test_re_registering_does_not_duplicate_fragments(client, signed_in, db):
    """Idempotent by content hash, so a retry adds nothing."""
    artifact = upload(client)
    register(client, artifact["id"])
    before = len(db.scalars(select(KnowledgeFragment)).all())

    from app.services.artifacts.fragments import build_for_artifact
    from app.services.artifacts.service import extracted_document

    row = db.scalars(select(Artifact)).one()
    added = build_for_artifact(db, row, document=extracted_document(row))
    db.commit()

    assert added == 0
    assert len(db.scalars(select(KnowledgeFragment)).all()) == before


# --- search ----------------------------------------------------------------

def test_search_finds_the_relevant_fragment_first(client, signed_in):
    artifact = upload(client)
    register(client, artifact["id"])

    r = client.post("/api/search", json={"query": "embeddings stored as float arrays"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert "float arrays" in body["matches"][0]["content"]
    # Scores come from a named space, so a provider change is visible.
    assert body["provider"] == "hashing"
    assert body["dimensions"] == 384
    assert body["matches"][0]["score"] > 0


def test_search_results_point_back_at_the_artifact(client, signed_in):
    artifact = upload(client)
    register(client, artifact["id"])

    match = client.post("/api/search", json={"query": "provenance"}).json()["matches"][0]
    assert match["artifact_id"] == artifact["id"]
    assert match["artifact_filename"] == "notes.txt"
    assert match["artifact_title"] == "Provenance Notes"
    assert "char_start" in match["source_location"]


def test_search_respects_the_limit(client, signed_in):
    artifact = upload(client, content="Alpha one.\n\nBeta two.\n\nGamma three.\n\nDelta four.\n")
    register(client, artifact["id"])

    body = client.post("/api/search", json={"query": "alpha", "limit": 1}).json()
    assert len(body["matches"]) == 1


def test_an_unrelated_query_returns_nothing(client, signed_in):
    """The hashing embedder is lexical. Say nothing rather than invent a match.

    A fragment with no lexical overlap scores zero or below. Such a fragment
    is not returned at all: presenting an unrelated passage as a weak match
    would be offering it as evidence for something it does not support.
    """
    artifact = upload(client)
    register(client, artifact["id"])

    body = client.post(
        "/api/search", json={"query": "xylophone marsupial quixotic"}
    ).json()
    assert body["matches"] == []
    assert body["total"] == 0


def test_only_related_fragments_come_back(client, signed_in):
    """A query matching one chunk must not drag its neighbours in."""
    artifact = upload(
        client,
        content="Embeddings are float arrays in PostgreSQL.\n\nHelvetica Garamond Futura.\n",
    )
    register(client, artifact["id"])

    body = client.post("/api/search", json={"query": "float arrays postgresql"}).json()
    assert body["total"] == 1
    assert "float arrays" in body["matches"][0]["content"]
    assert all(m["score"] > 0 for m in body["matches"])


def test_search_rejects_an_empty_query(client, signed_in):
    assert client.post("/api/search", json={"query": ""}).status_code == 422


def test_search_requires_a_session(client):
    assert client.post("/api/search", json={"query": "provenance"}).status_code == 401


# --- isolation -------------------------------------------------------------

def test_one_user_never_searches_another_users_knowledge(client, valid_signup):
    """Ownership is in the query predicate, not a check afterwards."""
    client.post("/api/auth/signup", json=valid_signup)
    owner = upload(client, "private.txt", "The passphrase is hunter-two-aardvark.\n")
    register(client, owner["id"], {"title": "Private", "topics": []})
    client.post("/api/auth/logout")

    client.post(
        "/api/auth/signup",
        json={
            "display_name": "Grace Hopper",
            "email": "grace@example.com",
            "password": "compiler-1952-nanoseconds",
        },
    )
    body = client.post("/api/search", json={"query": "passphrase hunter aardvark"}).json()
    assert body["matches"] == []
    assert body["total"] == 0


def test_deleting_an_artifact_removes_its_fragments(client, signed_in, db):
    artifact = upload(client)
    register(client, artifact["id"])
    assert db.scalars(select(KnowledgeFragment)).all() != []

    assert client.delete(f"/api/artifacts/{artifact['id']}").status_code == 204
    db.expire_all()
    assert db.scalars(select(KnowledgeFragment)).all() == []
    assert db.scalars(select(FragmentEmbedding)).all() == []


# --- integrity of the vector space -----------------------------------------

def test_a_failing_local_provider_refuses_registration(client, signed_in, db):
    """No fallback. The artifact stays unregistered and the user is told why.

    A provider that cannot embed must not be replaced by another: a different
    provider writes a different vector space, and a cloud one would send
    content the user never consented to send. Registering anyway would put an
    artifact in the library as trusted evidence that no query can reach.
    """
    import app.services.embeddings as embeddings
    from app.services.embeddings import reset_embedding_provider
    from app.services.embeddings.ollama import OllamaEmbedder

    artifact = upload(client)
    # A real provider pointed at a port with nothing on it — a genuine
    # failure, not a stubbed one.
    embeddings._provider = OllamaEmbedder(base_url="http://127.0.0.1:1")
    try:
        r = register(client, artifact["id"])
    finally:
        reset_embedding_provider()

    assert r.status_code == 503
    assert "ollama" in r.json()["detail"].lower()

    db.expire_all()
    row = db.scalars(select(Artifact)).one()
    assert row.status == "inspected"
    assert row.integrity["human_approved"] is False
    assert db.scalars(select(KnowledgeFragment)).all() == []

    # And nothing was made searchable.
    assert client.post("/api/search", json={"query": "provenance"}).json()["matches"] == []


def test_vectors_from_another_space_are_never_compared(client, signed_in, db):
    """A cosine similarity across two embedding spaces is meaningless.

    Fragments embedded at one width must not be scored against a query
    embedded at another, so search filters on provider, model and dimensions.
    """
    import app.services.embeddings as embeddings
    from app.services.embeddings import reset_embedding_provider
    from app.services.embeddings.hashing import HashingEmbedder

    artifact = upload(client)
    register(client, artifact["id"])
    # Semantic mode on purpose: the keyword half of a hybrid search does not
    # go near a vector, so it would match regardless and prove nothing here.
    semantic = {"query": "provenance", "mode": "semantic"}
    assert client.post("/api/search", json=semantic).json()["total"] >= 1

    # Same provider, different width — a different space, and the stored
    # vectors must drop out of the results rather than be compared.
    embeddings._provider = HashingEmbedder(dimensions=128)
    try:
        body = client.post("/api/search", json=semantic).json()
    finally:
        reset_embedding_provider()

    assert body["dimensions"] == 128
    assert body["matches"] == []


# --- unified search: modes, grouping, filters ------------------------------

SPEC = (
    "The retention schedule for ledger exports is seven years.\n\n"
    "Quarterly reconciliation is signed off by the finance lead.\n"
)


def test_keyword_mode_finds_an_exact_term_and_marks_the_passage(client, signed_in):
    artifact = upload(client, "retention.txt", SPEC)
    register(client, artifact["id"], {"title": "Retention Policy", "topics": ["Records"]})

    body = client.post(
        "/api/search", json={"query": "reconciliation", "mode": "keyword"}
    ).json()

    assert body["mode"] == "keyword"
    assert body["total_knowledge"] >= 1
    hit = body["knowledge"][0]
    # The excerpt is the passage around the match, with the term marked, not
    # the opening of the document.
    assert "<mark>" in hit["excerpt"].lower()
    assert hit["matched_by"] == ["keyword"]
    # Relevance is words, never a percentage.
    assert hit["relevance"] in {"Highly Related", "Related", "Potential Connection"}
    assert "%" not in hit["relevance"]


def test_keyword_mode_needs_no_embedding_provider(client, signed_in):
    """A keyword query must not touch a model, even a local one."""
    import app.services.embeddings as embeddings

    artifact = upload(client, "retention.txt", SPEC)
    register(client, artifact["id"])

    class Refuses:
        name, model, dimensions = "refuses", "none", 1

        def embed(self, texts):
            raise AssertionError("keyword search embedded a query")

    previous = embeddings._provider
    embeddings._provider = Refuses()
    try:
        body = client.post(
            "/api/search", json={"query": "reconciliation", "mode": "keyword"}
        ).json()
    finally:
        embeddings._provider = previous

    assert body["total_knowledge"] >= 1


def test_hybrid_fuses_both_retrievals(client, signed_in):
    artifact = upload(client, "retention.txt", SPEC)
    register(client, artifact["id"])

    body = client.post("/api/search", json={"query": "reconciliation"}).json()

    assert body["mode"] == "hybrid"
    # Something a keyword query matches literally should be found by both
    # halves, and the fused result says so.
    found_by = {m for hit in body["knowledge"] for m in hit["matched_by"]}
    assert "keyword" in found_by
    assert "semantic" in found_by


def test_a_quoted_query_is_a_phrase(client, signed_in):
    artifact = upload(client, "retention.txt", SPEC)
    register(client, artifact["id"])

    phrase = client.post(
        "/api/search", json={"query": '"retention schedule"', "mode": "keyword"}
    ).json()
    assert phrase["total_knowledge"] >= 1

    # The same words in the other order are not that phrase.
    reversed_phrase = client.post(
        "/api/search", json={"query": '"schedule retention"', "mode": "keyword"}
    ).json()
    assert reversed_phrase["total_knowledge"] == 0


def test_documents_match_on_their_own_metadata(client, signed_in):
    artifact = upload(client, "ledger-exports.txt", SPEC)
    register(client, artifact["id"], {"title": "Retention Policy", "tags": ["audit"]})

    body = client.post("/api/search", json={"query": "audit", "mode": "keyword"}).json()

    assert [d["filename"] for d in body["documents"]] == ["ledger-exports.txt"]
    assert body["documents"][0]["status"] == "registered"


def test_an_unapproved_document_is_findable_but_never_knowledge(client, signed_in):
    """A draft is still the user's document; it is just not established."""
    upload(client, "ledger-exports.txt", SPEC)

    body = client.post("/api/search", json={"query": "ledger exports"}).json()

    assert body["total_knowledge"] == 0
    # Extraction has run, so it is "inspected" — read, not established.
    assert [d["status"] for d in body["documents"]] == ["inspected"]


def test_scope_limits_which_groups_are_searched(client, signed_in):
    artifact = upload(client, "retention.txt", SPEC)
    register(client, artifact["id"], {"title": "Retention Policy", "tags": ["retention"]})

    library = client.post(
        "/api/search", json={"query": "retention", "scope": "library"}
    ).json()
    assert library["documents"] and library["knowledge"] == []

    knowledge = client.post(
        "/api/search", json={"query": "retention", "scope": "knowledge"}
    ).json()
    assert knowledge["knowledge"] and knowledge["documents"] == []


def test_filters_narrow_results_without_inventing_values(client, signed_in):
    artifact = upload(client, "retention.txt", SPEC)
    register(client, artifact["id"], {"title": "Retention Policy", "topics": ["Records"]})

    matching = client.post(
        "/api/search",
        json={"query": "reconciliation", "filters": {"topics": ["Records"]}},
    ).json()
    assert matching["total_knowledge"] >= 1

    other = client.post(
        "/api/search",
        json={"query": "reconciliation", "filters": {"topics": ["Finance"]}},
    ).json()
    assert other["total_knowledge"] == 0
    assert other["total_documents"] == 0


def test_concepts_come_from_confirmed_topics_only(client, signed_in):
    artifact = upload(client, "retention.txt", SPEC)
    register(client, artifact["id"], {"title": "Retention Policy", "topics": ["Records"]})

    body = client.post("/api/search", json={"query": "reconciliation"}).json()

    assert [c["label"] for c in body["concepts"]] == ["Records"]


def test_search_never_reaches_another_owner(client, signed_in, valid_signup):
    artifact = upload(client, "retention.txt", SPEC)
    register(client, artifact["id"])
    client.post("/api/auth/logout")

    other = dict(valid_signup, email="someone.else@example.com")
    client.post("/api/auth/signup", json=other)
    body = client.post("/api/search", json={"query": "reconciliation"}).json()

    assert body["total_knowledge"] == 0
    assert body["total_documents"] == 0


def test_suggestions_come_from_the_owners_own_metadata(client, signed_in):
    artifact = upload(client, "retention.txt", SPEC)
    register(
        client,
        artifact["id"],
        {"title": "Retention Policy", "topics": ["Records"], "tags": ["audit"]},
    )

    body = client.get("/api/search/suggestions", params={"q": "reten"}).json()
    assert "Retention Policy" in body["suggestions"]

    # An empty prefix suggests nothing rather than everything.
    assert client.get("/api/search/suggestions", params={"q": ""}).json()["suggestions"] == []


def test_suggestions_are_owner_scoped(client, signed_in, valid_signup):
    artifact = upload(client, "retention.txt", SPEC)
    register(client, artifact["id"], {"title": "Retention Policy"})
    client.post("/api/auth/logout")

    client.post("/api/auth/signup", json=dict(valid_signup, email="third@example.com"))
    assert client.get("/api/search/suggestions", params={"q": "reten"}).json()["suggestions"] == []


def test_suggestions_and_search_require_a_session(client):
    assert client.post("/api/search", json={"query": "anything"}).status_code == 401
    assert client.get("/api/search/suggestions", params={"q": "a"}).status_code == 401
