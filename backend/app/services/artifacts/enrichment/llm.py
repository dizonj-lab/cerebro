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
import urllib.error
import urllib.request

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
        body = self._ask(text[:MAX_PROMPT_CHARS])
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
        haystack = text.lower()

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
            grounded, dropped = _grounded(body.get(field), haystack, limit)
            if grounded:
                suggestions[field] = grounded
                methods[field] = "ai_suggested"
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
        )

    def _ask(self, text: str) -> dict | None:
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": _INSTRUCTION + text,
                "stream": False,
                "format": "json",
                # Deterministic decoding: the same document should enrich the
                # same way twice.
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - fixed http scheme, local daemon
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                envelope = json.loads(response.read().decode("utf-8"))
            parsed = json.loads(envelope.get("response") or "{}")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            # Unreachable, slow or not valid JSON. The caller reports that
            # only deterministic enrichment ran.
            return None
        return parsed if isinstance(parsed, dict) else None


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned[:1000] or None


def _grounded(value: object, haystack: str, limit: int) -> tuple[list[str], int]:
    """Keep only suggestions the document actually contains."""
    if not isinstance(value, list):
        return [], 0
    kept: list[str] = []
    seen: set[str] = set()
    dropped = 0
    for item in value:
        text = _clean_text(item)
        if text is None:
            continue
        if text.lower() in haystack:
            # Case-insensitively unique: "Digital Twin" and "digital twin"
            # are one topic, not two.
            if text.lower() not in seen:
                seen.add(text.lower())
                kept.append(text)
        else:
            dropped += 1
        if len(kept) == limit:
            break
    return kept, dropped
