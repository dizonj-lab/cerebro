"""The embedding and chunking budget, resolved per owner.

These five values decide whether a document can be registered at all. Until
now they were compiled-in constants and environment variables: when PDF
ingestion broke because a slide chunk overran mxbai-embed-large's 512-token
context, nobody could see what the numbers were, let alone correct them
without editing a file and rebuilding a container. They are settings now.

A null column means "whatever this deployment is configured with", so an
untouched account behaves exactly as before and a deployment default change
still reaches everyone who has not overridden it. Only a value a user
actually set is an override.

The two halves fail differently, and the settings screen says so:

* **Model and width** are matched against every stored vector at search
  time, so changing either **orphans the vectors already written**. The
  fragments are still there and still found by keyword; they drop out of
  semantic search until re-registered under the new model.
* **Context limit, target and overlap** only decide how the *next*
  registration is cut. Fragments already written keep the size they were
  cut at.

Nothing here can be used to reach another account's settings: every caller
resolves preferences from the session's own user.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import get_settings
from app.models.profile import UserPreferences
from app.services.artifacts import chunking
from app.services.artifacts import tokens as token_budget

# A model's published width and context. Getting either wrong is not a
# degraded embedding, it is a daemon that refuses every request, so where the
# model is known the stored value is checked against this rather than trusted.
KNOWN_DIMENSIONS = {
    "mxbai-embed-large": 1024,
    "nomic-embed-text": 768,
    "bge-m3": 1024,
    "all-minilm": 384,
}
KNOWN_CONTEXT = dict(token_budget.CONTEXT_TOKENS)

# Bounds for a hand-entered value. Generous — they exist to catch a typo
# (a missing digit, a pasted line) rather than to second-guess the user.
MIN_TARGET_TOKENS = 32
MAX_CONTEXT_TOKENS = 32768
MIN_CONTEXT_TOKENS = 64


def family_of(model: str | None) -> str:
    """The model name without its tag. 'mxbai-embed-large:latest' -> family."""
    return (model or "").split(":", 1)[0].strip().lower()


@dataclass(frozen=True)
class IngestSettings:
    """The budget one registration or one query is measured against."""

    # None means the provider keeps whatever it discovered or was configured
    # with. A user who has not chosen a model must not be pinned to one.
    embedding_model: str | None
    embedding_dimensions: int | None
    context_limit: int
    target_tokens: int
    overlap_tokens: int
    # Which of the five the user set, for the settings screen to mark and for
    # /api/ml/status to report. Provenance of a setting, like any other.
    overrides: frozenset[str] = field(default_factory=frozenset)

    @property
    def embeddable_tokens(self) -> int:
        """The limit the chunker must cut to.

        Smaller than `context_limit`, because the context has to hold the
        model's special tokens as well as the text. Cutting to the context
        produced chunks that sat exactly on the boundary and were refused.
        """
        return token_budget.payload_limit(self.embedding_model or "", self.context_limit)

    @property
    def target_chars(self) -> int:
        return int(self.target_tokens * chunking.CHARS_PER_TOKEN)

    @property
    def overlap_chars(self) -> int:
        return int(self.overlap_tokens * chunking.CHARS_PER_TOKEN)

    def with_model(self, model: str | None) -> IngestSettings:
        """The same budget, with the context limit tracking a given model.

        Used when the provider's model is known but the user pinned none: the
        limit must follow the model actually in use, not the default for a
        model nobody selected.
        """
        if self.embedding_model is not None or not model:
            return self
        known = KNOWN_CONTEXT.get(family_of(model))
        if known is None or "context_limit" in self.overrides:
            return self
        return IngestSettings(
            embedding_model=self.embedding_model,
            embedding_dimensions=self.embedding_dimensions,
            context_limit=known,
            target_tokens=min(self.target_tokens, max(known - 16, MIN_TARGET_TOKENS)),
            overlap_tokens=self.overlap_tokens,
            overrides=self.overrides,
        )


def deployment_default() -> IngestSettings:
    """What this deployment is configured with, before any user override."""
    settings = get_settings()
    model = settings.ollama_embedding_model if settings.embedding_provider == "ollama" else None
    return IngestSettings(
        embedding_model=None,
        embedding_dimensions=None,
        context_limit=token_budget.context_for(model or ""),
        target_tokens=chunking.TARGET_TOKENS,
        overlap_tokens=chunking.OVERLAP_TOKENS,
        overrides=frozenset(),
    )


def resolve(preferences: UserPreferences | None) -> IngestSettings:
    """Merge a user's overrides onto the deployment default.

    A null column is not a zero: it means the user never chose, so the
    deployment's value stands.
    """
    base = deployment_default()
    if preferences is None:
        return base

    overrides: set[str] = set()
    model = base.embedding_model
    if preferences.embedding_model:
        model = preferences.embedding_model
        overrides.add("embedding_model")

    dimensions = base.embedding_dimensions
    if preferences.embedding_dimensions:
        dimensions = preferences.embedding_dimensions
        overrides.add("embedding_dimensions")
    elif model is not None:
        # A chosen model with no stated width uses the published one, so the
        # pair can never disagree by omission.
        dimensions = KNOWN_DIMENSIONS.get(family_of(model), dimensions)

    context_limit = base.context_limit
    if preferences.embedding_context_limit:
        context_limit = preferences.embedding_context_limit
        overrides.add("context_limit")
    elif model is not None:
        context_limit = token_budget.context_for(model)

    target = base.target_tokens
    if preferences.chunk_target_tokens:
        target = preferences.chunk_target_tokens
        overrides.add("target_tokens")

    overlap = base.overlap_tokens
    if preferences.chunk_overlap_tokens is not None:
        overlap = preferences.chunk_overlap_tokens
        overrides.add("overlap_tokens")

    # Last-resort clamps. The schema rejects these combinations at the API
    # boundary; a row that predates a rule, or one written directly, must not
    # be able to produce a chunk the model cannot accept.
    target = max(MIN_TARGET_TOKENS, min(target, context_limit))
    overlap = max(0, min(overlap, target - 1))

    return IngestSettings(
        embedding_model=model,
        embedding_dimensions=dimensions,
        context_limit=context_limit,
        target_tokens=target,
        overlap_tokens=overlap,
        overrides=frozenset(overrides),
    )


class InvalidIngestSettings(ValueError):
    """A combination that would make registration fail. Reported as a 422."""


def check(preferences: UserPreferences) -> None:
    """Reject a combination that cannot work, before it is committed.

    This runs on the **merged** row rather than on the request, because a
    PATCH carries only what changed: a target of 900 is fine on its own and
    impossible against a stored 512-token limit. Checking the request alone
    would let the pair through one field at a time, which is how an
    unembeddable library gets written.
    """
    model = preferences.embedding_model
    family = family_of(model)

    stated_width = preferences.embedding_dimensions
    published_width = KNOWN_DIMENSIONS.get(family)
    if stated_width and published_width and stated_width != published_width:
        raise InvalidIngestSettings(
            f"{model} produces {published_width}-dimension vectors, not "
            f"{stated_width}. A wrong width is not a smaller vector; the "
            "daemon refuses every embedding. Leave it empty to use "
            f"{published_width}."
        )

    stated_limit = preferences.embedding_context_limit
    published_limit = KNOWN_CONTEXT.get(family)
    if stated_limit and published_limit and stated_limit > published_limit:
        raise InvalidIngestSettings(
            f"{model} has a {published_limit}-token context, so {stated_limit} "
            "would be rejected by the daemon for any chunk that used it. A "
            "lower limit is allowed; a higher one is the failure this setting "
            "exists to prevent."
        )

    # The effective limit, which is what the target has to fit inside.
    limit = stated_limit or published_limit or token_budget.DEFAULT_CONTEXT_TOKENS
    target = preferences.chunk_target_tokens
    overlap = preferences.chunk_overlap_tokens

    if target and target > limit:
        raise InvalidIngestSettings(
            f"A {target}-token chunk cannot be embedded by a model with a "
            f"{limit}-token context. Keep the target under the limit, with "
            "room to spare: the token count is an estimate, and the headroom "
            "is what absorbs it being wrong."
        )
    effective_target = target or chunking.TARGET_TOKENS
    if overlap is not None and overlap >= effective_target:
        raise InvalidIngestSettings(
            f"An overlap of {overlap} tokens is not smaller than the "
            f"{effective_target}-token chunk it overlaps, so chunking would "
            "never advance through the document."
        )


def for_user(db, user_id) -> IngestSettings:
    """The budget for one user, resolved from their own preferences row.

    Deliberately a plain read rather than `profiles.get_preferences`, which
    creates the row on first access. This runs on every search, every recall
    and every registration, and a read path that inserts is two problems: it
    makes a query a writer, and two enrichment workers resolving settings for
    the same new user at once would collide on the primary key. A missing row
    resolves to the deployment default, which is what a missing row means.
    """
    return resolve(db.get(UserPreferences, user_id))
