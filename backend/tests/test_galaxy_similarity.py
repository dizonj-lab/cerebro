"""Measured similarity in the Galaxy.

The properties that matter: a percentage is only ever a cosine similarity of
stored vectors, with the model named; what counts as similar is judged
against this library's own typical similarity; a passage resembling nothing
else says so rather than being linked anyway; and asking where text would
sit stores nothing. The suite pins the hashing embedder, so "alike" here
means shared words, and the response says exactly that.
"""
import pytest

from app.services.embeddings import EmbeddingFailed

AUDIO = (
    b"Speech recognition turns audio signals into text. Spectrogram features of "
    b"speech audio feed an acoustic model for recognition of spoken words.\n"
)
SPEECH = (
    b"Spoken words are recognised from speech audio. Acoustic models read spectrogram "
    b"features of speech signals for recognition of spoken text.\n"
)
# Gardening and accounting share no words at all — not even "the" — so with
# the hashing embedder they are genuinely unlike everything else here.
GARDEN = (
    b"Tomatoes need compost, sunlight, regular watering. Prune vines, mulch beds "
    b"early in summer to keep soil moist.\n"
)
LEDGER = (
    b"Quarterly invoices reconcile against ledgers; accounts payable closes books "
    b"once auditors sign balance sheets.\n"
)

@pytest.fixture
def library(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    for name, body, topic in (
        ("audio.txt", AUDIO, "Audio"),
        ("speech.txt", SPEECH, "Speech"),
        ("garden.txt", GARDEN, "Gardening"),
        ("ledger.txt", LEDGER, "Accounting"),
    ):
        artifact = client.post(
            "/api/artifacts", files={"file": (name, body, "text/plain")}
        ).json()
        client.patch(
            f"/api/artifacts/{artifact['id']}",
            json={
                "metadata": {**artifact["metadata"], "title": name, "topics": [topic]},
                "approve": True,
            },
        )


def test_the_galaxy_says_how_similarity_was_measured(client, library):
    space = client.get("/api/graph").json()["similarity"]

    assert space["provider"] == "hashing"
    assert space["learned"] is False
    # The hashing embedder compares words, and is never passed off as meaning.
    assert space["measures"] == "shared words"
    assert space["topics_measured"] == 4
    assert 0 <= space["typical"] < space["ceiling"] <= 1


def test_topics_that_never_share_a_document_can_still_be_found_alike(client, library):
    edges = client.get("/api/graph").json()["edges"]
    found = [e for e in edges if e["kind"] == "similar_words"]

    pair = next(e for e in found if {e["source"], e["target"]} == {"topic:Audio", "topic:Speech"})
    assert pair["discovered"] is True
    assert 0 < pair["similarity"] <= 1
    assert 0 <= pair["strength"] <= 1
    # The percentage is stated with the model that measured it, and the
    # explanation says plainly that alike is not related.
    assert f"{round(pair['similarity'] * 100)}%" in pair["confidence"]
    assert "hashing" in pair["confidence"]
    assert "not a verified link" in pair["explanation"]
    # Unrelated topics are not linked just because every pair has a number.
    assert not any("topic:Gardening" in (e["source"], e["target"]) for e in found)


def test_a_passage_links_to_the_other_topics_it_resembles(client, library):
    body = client.get("/api/graph/expand", params={"topic": "Audio"}).json()

    fragment = next(n for n in body["nodes"] if n["type"] == "fragment")
    assert fragment["orbit"] is False
    assert fragment["affinity"] == "Speech"
    assert 0 < fragment["similarity"] <= 1

    link = next(e for e in body["edges"] if e["target"] == "topic:Speech")
    assert link["source"] == fragment["id"]
    assert link["kind"] == "similar_words"
    assert link["relevance"] in ("Weak similarity", "Moderate similarity", "Strong similarity")


def test_a_passage_that_resembles_nothing_else_orbits_its_own_topic(client, library):
    body = client.get("/api/graph/expand", params={"topic": "Gardening"}).json()

    fragment = next(n for n in body["nodes"] if n["type"] == "fragment")
    assert fragment["orbit"] is True
    assert fragment["affinity"] is None
    # Only its own containment edge: nothing is linked for the sake of it.
    assert [e["kind"] for e in body["edges"]] == ["contains"]


def test_the_lens_places_text_without_storing_it(client, library):
    before = client.get("/api/artifacts").json()

    body = client.post(
        "/api/graph/lens", json={"text": "acoustic speech recognition of spoken audio"}
    ).json()

    assert {t["label"] for t in body["topics"][:2]} == {"Audio", "Speech"}
    assert body["topics"][0]["above_typical"] is True
    assert body["topics"][-1]["above_typical"] is False
    assert "closest to" in body["placement"]
    assert body["passages"] and body["passages"][0]["title"] in ("audio.txt", "speech.txt")
    assert client.get("/api/artifacts").json() == before


def test_text_unlike_anything_is_called_new_ground(client, library):
    body = client.post("/api/graph/lens", json={"text": "volcanic basalt magma eruption"}).json()
    assert "new ground" in body["placement"]


def test_the_lens_says_so_when_the_model_is_unreachable(client, library, monkeypatch):
    from app.services.embeddings.hashing import HashingEmbedder

    def unreachable(self, texts):
        raise EmbeddingFailed("daemon not reachable")

    monkeypatch.setattr(HashingEmbedder, "embed", unreachable)
    response = client.post("/api/graph/lens", json={"text": "speech audio"})
    assert response.status_code == 503
    assert "could not be reached" in response.json()["detail"]


def test_the_lens_requires_a_session(client):
    assert client.post("/api/graph/lens", json={"text": "speech"}).status_code == 401
