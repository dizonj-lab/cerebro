"""The embedding and chunking budget as a setting rather than a constant.

These five numbers decide whether a document can be registered at all. The
bug they came from — a slide chunk overrunning mxbai-embed-large's 512-token
context — was invisible because the numbers were compiled in. The tests here
hold the two properties that make them safe to expose: a combination that
cannot work is refused before it is stored, and a null column still means
"inherit the deployment default" rather than zero.
"""
import pytest

from app.core.config import get_settings
from app.models import UserPreferences
from app.services import ingest_settings
from app.services.artifacts import chunking, tokens
from app.services.artifacts.extraction import Block, SourceLocation

settings = get_settings()


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


class Row:
    """A preferences row's five fields, without needing the database."""

    def __init__(self, **kwargs):
        for field in (
            "embedding_model",
            "embedding_dimensions",
            "embedding_context_limit",
            "chunk_target_tokens",
            "chunk_overlap_tokens",
        ):
            setattr(self, field, kwargs.get(field))


# --- resolution -------------------------------------------------------------

def test_nulls_inherit_the_deployment_default():
    """An untouched account behaves exactly as before the setting existed."""
    resolved = ingest_settings.resolve(Row())
    default = ingest_settings.deployment_default()

    assert resolved.target_tokens == default.target_tokens == chunking.TARGET_TOKENS
    assert resolved.overlap_tokens == default.overlap_tokens == chunking.OVERLAP_TOKENS
    assert resolved.context_limit == default.context_limit
    # Nothing is pinned, so the provider keeps whatever it discovered.
    assert resolved.embedding_model is None
    assert resolved.overrides == frozenset()


def test_no_preferences_row_resolves_rather_than_failing():
    """A user who has never opened Settings still gets a usable budget."""
    resolved = ingest_settings.resolve(None)
    assert resolved.target_tokens > 0
    assert resolved.context_limit > 0


def test_a_chosen_model_brings_its_published_width_and_context():
    """Choosing a model must not require knowing its numbers."""
    resolved = ingest_settings.resolve(Row(embedding_model="mxbai-embed-large:latest"))

    assert resolved.embedding_dimensions == 1024
    assert resolved.context_limit == 512
    # Only the model was chosen, so only the model counts as overridden.
    assert resolved.overrides == {"embedding_model"}


def test_the_users_five_values_are_what_the_request_asked_for():
    resolved = ingest_settings.resolve(
        Row(
            embedding_model="mxbai-embed-large:latest",
            embedding_dimensions=1024,
            embedding_context_limit=512,
            chunk_target_tokens=350,
            chunk_overlap_tokens=50,
        )
    )
    assert resolved.embedding_model == "mxbai-embed-large:latest"
    assert resolved.embedding_dimensions == 1024
    assert resolved.context_limit == 512
    assert resolved.target_tokens == 350
    assert resolved.overlap_tokens == 50
    assert resolved.target_chars == 875


def test_a_zero_overlap_is_a_choice_not_an_omission():
    """0 is falsy; it must still read as an override rather than a default."""
    resolved = ingest_settings.resolve(Row(chunk_overlap_tokens=0))
    assert resolved.overlap_tokens == 0
    assert "overlap_tokens" in resolved.overrides


def test_a_stored_row_that_predates_a_rule_is_still_clamped():
    """Validation is at the API boundary; the resolver trusts nothing."""
    resolved = ingest_settings.resolve(
        Row(embedding_context_limit=256, chunk_target_tokens=4000, chunk_overlap_tokens=9000)
    )
    assert resolved.target_tokens <= resolved.context_limit
    assert resolved.overlap_tokens < resolved.target_tokens


def test_the_limit_follows_the_model_in_use_when_none_was_pinned():
    """A user who pinned nothing is measured against the live model."""
    resolved = ingest_settings.resolve(Row()).with_model("all-minilm")
    assert resolved.context_limit == 256
    assert resolved.target_tokens <= 256


def test_a_pinned_limit_is_not_overwritten_by_the_live_model():
    resolved = ingest_settings.resolve(Row(embedding_context_limit=200)).with_model("bge-m3")
    assert resolved.context_limit == 200


# --- refusing a combination that cannot work --------------------------------

def test_a_wrong_width_is_refused_with_the_right_one_named():
    with pytest.raises(ingest_settings.InvalidIngestSettings) as exc:
        ingest_settings.check(
            Row(embedding_model="mxbai-embed-large:latest", embedding_dimensions=768)
        )
    assert "1024" in str(exc.value)


def test_a_limit_above_the_models_context_is_refused():
    """Guessing high is the exact mistake that broke PDF ingestion."""
    with pytest.raises(ingest_settings.InvalidIngestSettings):
        ingest_settings.check(
            Row(embedding_model="mxbai-embed-large:latest", embedding_context_limit=2048)
        )


def test_a_limit_below_the_models_context_is_allowed():
    """Narrowing the budget is always safe; only widening it is not."""
    ingest_settings.check(
        Row(embedding_model="mxbai-embed-large:latest", embedding_context_limit=256)
    )


def test_a_chunk_larger_than_the_context_is_refused():
    with pytest.raises(ingest_settings.InvalidIngestSettings):
        ingest_settings.check(
            Row(embedding_context_limit=512, chunk_target_tokens=900)
        )


def test_an_overlap_that_never_advances_is_refused():
    with pytest.raises(ingest_settings.InvalidIngestSettings):
        ingest_settings.check(Row(chunk_target_tokens=100, chunk_overlap_tokens=100))


def test_an_unknown_model_is_not_second_guessed():
    """A model CEREBRO has no table entry for is the user's to describe."""
    ingest_settings.check(
        Row(
            embedding_model="some-local-build:q4",
            embedding_dimensions=1536,
            embedding_context_limit=8192,
            chunk_target_tokens=2000,
        )
    )


# --- the budget actually reaches the splitter -------------------------------

def test_a_smaller_limit_produces_smaller_chunks():
    """The setting has to change the output, not just be stored."""
    text = " ".join(f"token{i} fragment of slide text." for i in range(400))
    blocks = [Block(text, SourceLocation(page=1, char_start=0, char_end=len(text)), "paragraph")]

    narrow = chunking.chunk_blocks(blocks, chunk_chars=250, overlap_chars=20, limit_tokens=120)
    wide = chunking.chunk_blocks(blocks, chunk_chars=875, overlap_chars=125, limit_tokens=512)

    assert len(narrow) > len(wide)
    assert all(tokens.estimate(c.content) <= 120 for c in narrow)
    assert all(tokens.estimate(c.content) <= 512 for c in wide)


def test_the_recorded_provenance_names_the_budget_used():
    """'Which splitter' no longer answers 'why is this fragment this size'."""
    provenance = chunking.chunking_provenance(
        [], chunk_chars=500, overlap_chars=60, target_tokens=200, limit_tokens=256
    )
    assert provenance["target_tokens"] == 200
    assert provenance["limit_tokens"] == 256


# --- the provider --------------------------------------------------------

def test_no_pinned_model_keeps_the_deployment_provider():
    from app.services import embeddings

    resolved = ingest_settings.resolve(Row())
    assert embeddings.provider_for(resolved) is embeddings.get_embedding_provider()


def test_a_pinned_model_carries_its_limit_onto_the_provider():
    """The pre-send check reads the limit off the provider, so it must land."""
    from app.services import embeddings

    resolved = ingest_settings.resolve(
        Row(
            embedding_model="mxbai-embed-large:latest",
            embedding_dimensions=1024,
            embedding_context_limit=256,
        )
    )
    provider = embeddings.provider_for(resolved)
    assert provider.model == "mxbai-embed-large:latest"
    assert provider.dimensions == 1024
    assert provider.context_limit == 256
    # Built once and shared, not per request.
    assert embeddings.provider_for(resolved) is provider


def test_an_oversized_chunk_is_refused_against_the_users_lower_limit():
    """A narrowed limit must be enforced, not merely recorded.

    Checked at the guard rather than through `embed`, which now splits an
    oversized input instead of refusing it. The limit the guard applies is
    the user's, less the room the special tokens need.
    """
    from app.services.artifacts import tokens as token_budget
    from app.services.embeddings import EmbeddingFailed
    from app.services.embeddings.ollama import OllamaEmbedder

    provider = OllamaEmbedder(
        model="mxbai-embed-large:latest", dimensions=1024, context_limit=100
    )
    text = " ".join(f"word{i}" for i in range(300))
    with pytest.raises(EmbeddingFailed) as exc:
        provider._post("/api/embed", {"model": provider.model, "input": text}, 5)

    assert str(token_budget.payload_limit(provider.model, 100)) in str(exc.value)
    assert "Nothing was sent" in str(exc.value)


def test_resolving_a_budget_never_writes_a_preferences_row(db, client, signed_in):
    """Search and recall resolve settings on every query; neither may insert.

    `profiles.get_preferences` creates the row on first access, which would
    make a read path a writer and let two enrichment workers collide on the
    primary key for the same new user.
    """
    db.query(UserPreferences).delete()
    db.commit()

    resolved = ingest_settings.for_user(db, _only_user_id(db))

    assert resolved.target_tokens == chunking.TARGET_TOKENS
    db.expire_all()
    assert db.query(UserPreferences).count() == 0


def _only_user_id(db):
    from app.models import User

    return db.query(User).one().id


# --- the API ----------------------------------------------------------------

def test_preferences_report_what_is_in_force_not_only_what_is_stored(client, signed_in):
    body = client.get("/api/preferences").json()

    assert body["embedding_model"] is None
    effective = body["effective"]
    assert effective["chunk_target_tokens"] == chunking.TARGET_TOKENS
    assert effective["chunk_overlap_tokens"] == chunking.OVERLAP_TOKENS
    assert effective["embedding_context_limit"] > 0
    assert effective["overridden"] == []


def test_the_five_settings_persist_and_are_marked_as_chosen(client, signed_in, db):
    response = client.patch(
        "/api/preferences",
        json={
            "embedding_model": "mxbai-embed-large:latest",
            "embedding_dimensions": 1024,
            "embedding_context_limit": 512,
            "chunk_target_tokens": 350,
            "chunk_overlap_tokens": 50,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["embedding_model"] == "mxbai-embed-large:latest"
    assert set(body["effective"]["overridden"]) == {
        "embedding_model",
        "embedding_dimensions",
        "context_limit",
        "target_tokens",
        "overlap_tokens",
    }

    stored = db.query(UserPreferences).one()
    assert stored.chunk_target_tokens == 350
    assert stored.embedding_dimensions == 1024


def test_a_contradictory_pair_is_refused_and_nothing_is_stored(client, signed_in, db):
    """The pair is checked on the merged row, not field by field."""
    client.patch("/api/preferences", json={"embedding_context_limit": 512})

    response = client.patch("/api/preferences", json={"chunk_target_tokens": 900})
    assert response.status_code == 422
    assert "512" in response.json()["detail"]

    stored = db.query(UserPreferences).one()
    assert stored.chunk_target_tokens is None
    assert stored.embedding_context_limit == 512


def test_a_wrong_width_is_refused_at_the_api(client, signed_in):
    response = client.patch(
        "/api/preferences",
        json={"embedding_model": "mxbai-embed-large:latest", "embedding_dimensions": 384},
    )
    assert response.status_code == 422
    assert "1024" in response.json()["detail"]


def test_a_setting_can_be_returned_to_the_deployment_default(client, signed_in):
    client.patch("/api/preferences", json={"chunk_target_tokens": 200})
    assert client.get("/api/preferences").json()["chunk_target_tokens"] == 200

    body = client.patch("/api/preferences", json={"chunk_target_tokens": None}).json()
    assert body["chunk_target_tokens"] is None
    assert body["effective"]["chunk_target_tokens"] == chunking.TARGET_TOKENS
    assert "target_tokens" not in body["effective"]["overridden"]


def test_a_typo_is_caught_by_the_field_bounds(client, signed_in):
    """35 tokens is a choice; 3 is a missing digit."""
    assert client.patch("/api/preferences", json={"chunk_target_tokens": 3}).status_code == 422
    assert (
        client.patch("/api/preferences", json={"embedding_context_limit": 999999}).status_code
        == 422
    )


def test_ml_status_reports_the_budget_beside_the_coverage_it_explains(client, signed_in):
    """"missing" is usually a changed model; these are the numbers behind it."""
    client.patch("/api/preferences", json={"chunk_target_tokens": 220})

    budget = client.get("/api/ml/status").json()["budget"]
    assert budget["chunk_target_tokens"] == 220
    assert budget["context_limit"] >= budget["chunk_target_tokens"]
    # The usable limit is reported too, and is smaller than the context.
    assert budget["payload_limit"] < budget["context_limit"]
    assert "target_tokens" in budget["overridden"]


def test_one_users_budget_does_not_reach_another(client, signed_in, valid_signup):
    """Settings are resolved from the session's own user, never a request."""
    client.patch("/api/preferences", json={"chunk_target_tokens": 120})

    original = client.cookies.get(settings.cookie_name)
    client.cookies.clear()
    client.post(
        "/api/auth/signup",
        json={**valid_signup, "email": "grace@example.com", "display_name": "Grace Hopper"},
    )
    body = client.get("/api/preferences").json()
    assert body["chunk_target_tokens"] is None
    assert body["effective"]["chunk_target_tokens"] == chunking.TARGET_TOKENS

    client.cookies.set(settings.cookie_name, original)
    assert client.get("/api/preferences").json()["chunk_target_tokens"] == 120
