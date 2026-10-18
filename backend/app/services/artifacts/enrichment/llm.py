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
import time

from app.services import ollama
from app.services.ollama import ENRICHMENT_TIMEOUT_SECONDS
from app.services.artifacts.enrichment.base import Enrichment

_TIMEOUT_SECONDS = 120
# Enough to characterise a document without sending all of a long one.
MAX_PROMPT_CHARS = 6000

_INSTRUCTION = """You are given the text of a document. Reply with JSON only, \
no prose, no code fences, matching exactly this shape:

{"title": string or null, "description": string or null, \
"topics": array of strings, "tags": array of strings, \
"people": array of strings, "organizations": array of strings, \
"projects": array of strings, "technologies": array of strings, \
"concepts": array of strings}

Rules:
- title: the document's actual subject, as its own heading states it. A
  lecture deck is named by its topic, not by "PowerPoint Presentation" or
  the file it was exported from. Null if the text does not make it clear.
- description: at most two sentences describing what the document is about.
- topics: up to 6 subjects, each a phrase that appears in the text verbatim.
- tags: up to 8 single keywords, each a word that appears in the text.
- people: named individuals the text mentions, spelled exactly as the text
  spells them, **including the presenter, lecturer or author printed on the
  first page** — a deck names the person giving it and that person belongs
  here. Keep any honorific the text uses. Only actual people: not
  companies, teams or job titles.
- organizations: companies, institutions and bodies the text names, spelled
  exactly as the text spells them.
- projects: named projects, products or initiatives, spelled exactly as the
  text spells them.
- technologies: named tools, languages, frameworks, platforms and standards
  the text mentions, spelled exactly as the text spells them.
- concepts: the ideas and methods the document is about, each a phrase that
  appears in the text.
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

    def enrich(
        self, *, text: str, properties: dict, filename: str, on_progress=None
    ) -> Enrichment:
        # A long document is read in windows rather than truncated: the
        # people and projects in a 29-page deck are mostly not in its first
        # six thousand characters. Each window is a separate, bounded call —
        # nothing is sent that exceeds the model's context — and the results
        # are merged.
        #
        # The windows share one **time budget**. Capping their number was not
        # enough: ten windows at the per-call timeout is half an hour inside a
        # single HTTP request, which no client waits for. The browser's proxy
        # gives up around five minutes and reports the API as unreachable —
        # which is both wrong and unhelpful, since the API is working and the
        # model is merely slow.
        #
        # So the budget is spent rather than the clock run out: whatever has
        # been read when it runs low is what gets merged, and the shortfall is
        # recorded in the notes. Partial suggestions a human reviews are worth
        # more than a request that dies.
        #
        # Windows are read **ends first**. What metadata needs — the title,
        # the byline, the subject, and whatever a document concludes — sits
        # at the front and the back; the middle is elaboration. Reading in
        # page order spent the budget on the elaboration of a forty-page
        # deck and never reached either end, which is how a lecture deck
        # came back named after the program that exported it.
        started = time.monotonic()
        windows = _ends_first(_windows(text))
        bodies: list[dict] = []
        read: list[str] = []
        unread = 0
        if on_progress:
            # Said before the first call, so a queue shows "0 of 4" rather
            # than nothing while the slowest part of the job starts.
            on_progress(0, len(windows), self.model)
        for index, window in enumerate(windows):
            spent = time.monotonic() - started
            # Stop before starting a call that could outlast the budget,
            # rather than after one has already blown it.
            if index and spent + ENRICHMENT_TIMEOUT_SECONDS > ENRICHMENT_BUDGET_SECONDS:
                unread = len(windows) - index
                break
            found = self._ask(window)
            read.append(window)
            if found is not None:
                bodies.append(found)
            if on_progress:
                on_progress(index + 1, len(windows), self.model)
        body = _merge(bodies) if bodies else None
        # Grounding is checked against exactly what was read — the windows
        # actually sent, not every window the document has. Joining all of
        # them would let a suggestion be "found" in a part the model never
        # saw, which is coincidence wearing the costume of evidence. The
        # time budget made that reachable: before it, every window was read.
        text = "\n".join(read)
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
        empty_fields: list[str] = []
        haystack = text

        if unread:
            # Said plainly: these suggestions describe part of the document,
            # and the user can ask again for the rest.
            notes.append(
                f"Read {len(bodies)} of {len(windows)} sections before the time "
                f"budget ran out; {unread} were not read. The suggestions below "
                "cover only what was read."
            )

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
            ("technologies", 12),
            ("concepts", 8),
        ):
            grounded, dropped, found = _grounded(
                body.get(field), haystack, limit, source=text
            )
            if not grounded and not dropped and body.get(field) in (None, [], ""):
                # The model offered nothing for this field. Worth saying,
                # because an empty People box looks identical whether the
                # model proposed nobody or proposed people the guard then
                # removed — and those need opposite fixes.
                empty_fields.append(field)
            if grounded:
                suggestions[field] = grounded
                methods[field] = "ai_suggested"
                evidence.update(found)
            if dropped:
                # Recorded rather than hidden: a model that keeps proposing
                # absent phrases is a model to stop trusting.
                # Named, not counted. A count makes a dropped suggestion
                # invisible: the field is empty and nothing says what was
                # removed or why, so a grounding guard doing its job is
                # indistinguishable from a model proposing nothing.
                removed = _removed_values(body.get(field), grounded)
                notes.append(
                    f"Dropped {dropped} suggested {field} not found in the document"
                    + (f": {', '.join(removed[:6])}" if removed else "")
                    + ("…" if len(removed) > 6 else ".")
                )

        if empty_fields:
            notes.append(
                f"The model proposed nothing for: {', '.join(empty_fields)}."
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
                timeout=ENRICHMENT_TIMEOUT_SECONDS,
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


def _removed_values(proposed: object, kept: list[str]) -> list[str]:
    """What the guard took out, as the model wrote it."""
    if not isinstance(proposed, list):
        return []
    survived = {k.strip().lower() for k in kept}
    return [
        " ".join(str(item).split())
        for item in proposed
        if isinstance(item, str) and " ".join(item.split()).lower() not in survived
    ]


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


# A window is sized to the prompt budget; the cap bounds what one document
# can cost. Ten windows of 6000 characters covers roughly sixty pages, after
# which the remainder is not read rather than read badly.
MAX_WINDOWS = 10
# The whole of one enrichment, across every window. A local model on a laptop
# is slow, and a request nobody waits for is worth nothing however complete it
# would have been. Sized to stay well inside the browser proxy's own patience.
ENRICHMENT_BUDGET_SECONDS = 150


def _ends_first(windows: list[str]) -> list[str]:
    """First, last, then inward.

    A document introduces itself at the front and concludes at the back, and
    a budget that runs out should have spent itself on those rather than on
    the middle. Order only: nothing is skipped, and a document whose budget
    is sufficient still reads all of it.
    """
    out: list[str] = []
    left, right = 0, len(windows) - 1
    while left <= right:
        out.append(windows[left])
        if left != right:
            out.append(windows[right])
        left += 1
        right -= 1
    return out


def _windows(text: str) -> list[str]:
    """Split a long document into bounded, slightly overlapping reads.

    The overlap matters: a name landing on a window boundary would otherwise
    be cut in half and found in neither.
    """
    if len(text) <= MAX_PROMPT_CHARS:
        return [text]

    overlap = 200
    out: list[str] = []
    start = 0
    while start < len(text) and len(out) < MAX_WINDOWS:
        out.append(text[start : start + MAX_PROMPT_CHARS])
        start += MAX_PROMPT_CHARS - overlap
    return out


def _merge(bodies: list[dict]) -> dict:
    """Combine window replies: first title and description, union of lists.

    The first window's title is the document's title — later windows are
    looking at its middle, where a heading is a section, not the document.
    """
    merged: dict = {}
    # Author and date are carried through deliberately, though no engine may
    # propose them: the handler downstream records that a model tried, and
    # dropping them here would silence that.
    for key in ("title", "description", "author", "created_date", "date"):
        for body in bodies:
            value = _clean_text(body.get(key))
            if value:
                merged[key] = value
                break

    for key in (
        "topics",
        "tags",
        "people",
        "organizations",
        "projects",
        "technologies",
        "concepts",
    ):
        seen: set[str] = set()
        values: list[str] = []
        for body in bodies:
            for item in body.get(key) or []:
                text = _clean_text(item)
                if text and text.lower() not in seen:
                    seen.add(text.lower())
                    values.append(text)
        if values:
            merged[key] = values
    return merged
