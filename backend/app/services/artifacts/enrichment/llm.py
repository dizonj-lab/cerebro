"""Enrichment by a language model running locally, through Ollama.

Opt-in, because it needs a model pulled first:

    ollama pull llama3.2

Ollama is a daemon on the user's own machine, so the document does not leave
the CEREBRO environment. There is no cloud engine here and a failure never
becomes one: if the model is unreachable, enrichment falls back to the
deterministic engine, which is local too.

What a model may propose is deliberately narrow:

* `title` and `description` — generative by nature, labelled `ai_suggested`,
  and never presented as established fact.
* `topics`, `tags`, `people`, `organizations` and `projects` — checked
  against the document before being accepted. An entry the document does not
  contain is dropped, however plausible. This is the guard that stops a model
  inventing subject matter or, worse, inventing a person.

  Naming the people and organizations a document mentions is the one thing
  here that statistics cannot do: telling a person from a company needs
  knowledge of the world, not word counts. It is also where a model is most
  tempting to trust and least safe to, so the grounding check matters most.

It may not propose an author or a creation date at all. Those are claims
about the world, and a model reading the text cannot establish them.
"""
from __future__ import annotations

import json
import re

from app.services import ollama
from app.services.artifacts.enrichment.base import Enrichment

_TIMEOUT_SECONDS = 120
# Enough to characterise a document without sending all of a long one.
MAX_PROMPT_CHARS = 6000

_INSTRUCTION = """You are given the text of a document. Reply with JSON only, \
no prose, no code fences, matching exactly this shape:

{"title": string or null, "description": string or null, \
"topics": array of strings, "tags": array of strings, \
"people": array of strings, "organizations": array of strings, \
"projects": array of strings}

Rules:
- title: the document's actual title if the text makes it clear, else null.
- description: at most two sentences describing what the document is about.
- topics: up to 6 subjects, each a phrase that appears in the text verbatim.
- tags: up to 8 single keywords, each a word that appears in the text.
- people: named individuals the text mentions, spelled exactly as the text
  spells them. Only actual people. Not companies, teams or job titles.
- organizations: companies, institutions and bodies the text names, spelled
  exactly as the text spells them.
- projects: named projects, products or initiatives, spelled exactly as the
  text spells them.
- Every entry in every array must appear in the text word for word. If you
  cannot find it in the text, leave it out.
- Do not guess an author or a date. Do not invent anything not in the text.
- If the text is too short or unclear to judge, use null and empty arrays.

Document text:
"""


class OllamaEnricher:
    name = "ollama"
    ai_used = True
    # A local daemon. Content stays in the CEREBRO environment.
    local = True

    def __init__(self, *, base_url: str = "http://localhost:11434", model: str = "llama3.2"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def enrich(self, *, text: str, properties: dict, filename: str) -> Enrichment:
        # The model only sees the opening of a long document, so grounding is
        # checked against that same span: a name "found" in a part the model
        # never read would be a coincidence, not evidence.
        text = text[:MAX_PROMPT_CHARS]
        body = self._ask(text)
        if body is None:
            return Enrichment(
                engine=self.name,
                model=self.model,
                ai_used=False,
                notes=[
                    f"The local model '{self.model}' could not be reached, so only "
                    "deterministic enrichment ran."
                ],
            )

        suggestions: dict = {}
        methods: dict = {}
        notes: list[str] = []
        evidence: dict = {}
        haystack = text

        title = _clean_text(body.get("title"))
        if title:
            suggestions["title"] = title
            methods["title"] = "ai_suggested"

        description = _clean_text(body.get("description"))
        if description:
            suggestions["description"] = description
            methods["description"] = "ai_suggested"

        for field, limit in (
            ("topics", 6),
            ("tags", 8),
            ("people", 12),
            ("organizations", 12),
            ("projects", 12),
        ):
            grounded, dropped, found = _grounded(
                body.get(field), haystack, limit, source=text
            )
            if grounded:
                suggestions[field] = grounded
                methods[field] = "ai_suggested"
                evidence.update(found)
            if dropped:
                # Recorded rather than hidden: a model that keeps proposing
                # absent phrases is a model to stop trusting.
                notes.append(
                    f"Dropped {dropped} suggested {field} not found in the document."
                )

        for forbidden in ("author", "created_date", "date"):
            if body.get(forbidden):
                notes.append(
                    f"Ignored a suggested {forbidden}: only the document's own "
                    "metadata may establish that."
                )

        return Enrichment(
            suggestions=suggestions,
            methods=methods,
            engine=self.name,
            model=self.model,
            ai_used=True,
            local=True,
            notes=notes,
            evidence=evidence,
        )

    def _ask(self, text: str) -> dict | None:
        """One JSON reply from the local model, or None.

        The shared client handles the parts that are easy to get wrong per
        caller: a reasoning model's <think> block (which would make this
        reply unparseable), the timeout, and recording what ran.
        """
        try:
            generated = ollama.generate(
                self.base_url,
                self.model,
                _INSTRUCTION + text,
                operation="enrichment.suggest",
                fmt="json",
            )
        except ollama.OllamaUnavailable:
            # The caller reports that only deterministic enrichment ran. It
            # never becomes a cloud call.
            return None

        try:
            parsed = json.loads(generated.text or "{}")
        except json.JSONDecodeError:
            # Some models wrap JSON in prose or a code fence even when asked
            # not to. Recover the object rather than losing the whole reply.
            match = re.search(r"\{.*\}", generated.text, re.DOTALL)
            if not match:
                return None
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return parsed if isinstance(parsed, dict) else None


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned[:1000] or None


# Everything that is not a letter, digit or space becomes a space, and runs
# of space collapse. This is what lets "Acme, Inc." match a document that
# writes "Acme Inc", and a name broken across a line in a PDF match the same
# name written inline — without loosening the rule that it must be in the
# document.
_NOISE = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE = re.compile(r"\s+")
# A trailing gloss the model adds itself: "Maria Santos (CTO)". The gloss is
# not in the document and must not be, but the name is.
_PARENTHETICAL = re.compile(r"\s*\([^)]*\)\s*$")


def normalise(text: str) -> str:
    return _SPACE.sub(" ", _NOISE.sub(" ", text.lower())).strip()


def _evidence(needle: str, text: str) -> str | None:
    """The sentence the value was found in, for a human to check."""
    flat = _SPACE.sub(" ", text)
    position = normalise(flat).find(normalise(needle))
    if position == -1:
        return None
    # Normalisation can shift offsets, so the window is approximate on
    # purpose: it is a quote to read, not a citation to compute with.
    start = max(0, position - 90)
    return flat[start : position + len(needle) + 90].strip()


def _grounded(
    value: object, haystack: str, limit: int, *, source: str = ""
) -> tuple[list[str], int, dict]:
    """Keep only suggestions the document actually contains.

    The check is the guard against a model inventing a person, so it stays a
    containment test against the document. What changed is that both sides
    are normalised first: the old exact-substring test dropped "Acme, Inc."
    and "Maria Santos (CTO)" even though the document named both, which is
    why People, Organizations and Projects came back empty on documents that
    plainly contained them.
    """
    if not isinstance(value, list):
        return [], 0, {}
    kept: list[str] = []
    seen: set[str] = set()
    evidence: dict = {}
    dropped = 0
    normalised_haystack = normalise(haystack)

    for item in value:
        text = _clean_text(item)
        if text is None:
            continue
        candidate = _PARENTHETICAL.sub("", text).strip() or text
        needle = normalise(candidate)
        # A single character is not an entity, and would match anything.
        if len(needle) < 2 or needle not in normalised_haystack:
            dropped += 1
            continue
        # Case-insensitively unique: "Digital Twin" and "digital twin" are
        # one topic, not two.
        if needle in seen:
            continue
        seen.add(needle)
        kept.append(candidate)
        quote = _evidence(candidate, source) if source else None
        if quote:
            evidence[candidate] = quote
        if len(kept) == limit:
            break
    return kept, dropped, evidence
