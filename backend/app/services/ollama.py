"""One client for the local Ollama daemon: discovery, generation, embedding.

Ollama was reachable from three places in this codebase, each with its own
URL, its own timeout and its own idea of what to do when the daemon is not
there. This is the single place that talks to it.

Two things it does that the previous code did not:

* **Discovery.** It asks the daemon what is installed (`GET /api/tags`) and
  picks a model from what is actually there, rather than requiring the user
  to name one in an environment variable and failing silently when the name
  is wrong. A feature that depends on configuration nobody set is a feature
  that is off.
* **Telemetry.** Every call records the model, the duration and the token
  counts the daemon reports, so what ran is visible rather than claimed.

What it will not do: reach anything but a local daemon, or fall back to a
remote service. There is no cloud path in CEREBRO, and a failing local model
does not become one.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.services.telemetry import record

# Discovery is cheap but not free, and the answer rarely changes. Long enough
# that a conversation does not re-probe per message, short enough that
# pulling a model shows up without a restart.
DISCOVERY_TTL_SECONDS = 30
DISCOVERY_TIMEOUT_SECONDS = 2
GENERATE_TIMEOUT_SECONDS = 180
# Enrichment proposes a small JSON object about one window of a document.
# That is a short generation, and a call still running after a minute is
# stuck rather than thorough — so it is abandoned, and the windows that
# remain are read with the time it would have wasted.
ENRICHMENT_TIMEOUT_SECONDS = 60
EMBED_TIMEOUT_SECONDS = 60

# Preference order for answering. Small and instruction-following first: this
# is a summarise-these-passages job, not a reasoning benchmark, and a 3B
# model that replies in two seconds is worth more here than a 70B that takes
# a minute on a laptop.
# Enrichment asks for a small JSON object about one window of a document.
# A reasoning model deliberates first and then answers, which for this task
# is time spent producing text that is thrown away — qwen3's <think> block
# has to be stripped before the JSON can even be parsed. So enrichment
# prefers a model that answers directly, and falls back to the chat list
# when none is installed. Answering a question is the opposite case, and
# keeps its own order.
ENRICHMENT_PREFERENCES = (
    "qwen2.5",
    "llama3.2",
    "llama3.1",
    "mistral",
    "phi3.5",
    "phi3",
    "gemma2",
    "llama3",
    "qwen3",
)

CHAT_PREFERENCES = (
    "qwen3",
    "llama3.2",
    "llama3.1",
    "qwen2.5",
    "mistral",
    "phi3.5",
    "phi3",
    "gemma2",
    "llama3",
)

# Embedding models, best first. Both are purpose-built embedders; a chat
# model used for embeddings produces worse vectors slower.
EMBEDDING_PREFERENCES = (
    "mxbai-embed-large",
    "nomic-embed-text",
    "bge-m3",
    "all-minilm",
)

# Known widths, so a model can be selected without a probe request. An
# unknown model is measured on first use instead of assumed.
EMBEDDING_DIMENSIONS = {
    "mxbai-embed-large": 1024,
    "nomic-embed-text": 768,
    "bge-m3": 1024,
    "all-minilm": 384,
}


# Reasoning models (qwen3, deepseek-r1) emit their deliberation inside
# <think> tags before the answer. It is not part of the answer: shown to the
# user it reads as the model talking to itself, and left in a JSON reply it
# makes the reply unparseable. It is stripped from the text and never
# streamed, while `think: false` asks the newer daemons not to produce it at
# all — harmless on a daemon or model that does not know the option.
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


# Turning <think> off does not turn deliberating off. A reasoning model asked
# for `think: false` stops emitting the tag and then reasons in plain prose
# instead — restating the question, counting the passages, listing back the
# rules it was given — which nothing was stripping, so it reached the user as
# though it were the answer. The tag was never the problem; it was the only
# part that was easy to find.
#
# These are the openings that mark a model talking about the task rather than
# answering it. Matched only at the start of a line, and only while still in
# the preamble: "We have two options here" is a fine sentence in an answer,
# and must survive if it arrives after real prose has started.
_DELIBERATION = re.compile(
    r"""^\s*(?:
        we\s+(?:are\s+given|have|must|need|should|will|can)\b
      | (?:the\s+)?(?:user|question)\s+(?:is|asks|wants|has)\b
      | (?:okay|ok|alright|right|so|now|hmm)\b\s*[,:]
      | let(?:'s|\s+us|\s+me)\b
      | first(?:ly)?[,:]\s*(?:i|we|let)\b
      | i\s+(?:need|should|must|will|am\s+asked|have)\s+to\b
      | i'?ll\s+(?:start|begin|answer|write)\b
      | my\s+answer\s+(?:should|must|will)\b
      | the\s+task\s+is\b
      | looking\s+at\s+the\s+(?:passages?|documents?|question)\b
      | (?:key\s+)?rules?\s*:
      | (?:instructions?|guidelines?|constraints?|requirements?)\s*:
      | (?:step\s+\d+|plan)\s*:
    )""",
    re.IGNORECASE | re.VERBOSE,
)
# Every opener above starts with one of these words. Checking the first word
# alone decides almost every response: "Seven years [1]." is released the
# moment the first space arrives, so a normal answer streams word by word
# exactly as before. Only a response that genuinely opens with one of these
# is held long enough to run the full pattern.
_DELIBERATION_FIRST_WORDS = frozenset(
    """we the user question okay ok alright right so now hmm let let's lets
    first firstly i i'll ill my task key rules rule instructions instruction
    guidelines guideline constraints constraint requirements requirement step
    plan looking""".split()
)
# Enough to run the full pattern against, once the first word says it might
# be deliberation. The longest opener above is "looking at the passages", so
# this is conclusive — and short, because the common words are common: "The
# retention schedule says…" opens with a word on that list and must not be
# held back any longer than it takes to rule the pattern out.
_PREAMBLE_SAMPLE = 32
# Never hold back more than this. If a model deliberates past it, showing the
# deliberation is better than showing nothing at all.
_PREAMBLE_CAP = 4000


def _is_deliberation(paragraph: str) -> bool:
    """Whether a paragraph is the model thinking rather than answering."""
    lines = [line for line in paragraph.splitlines() if line.strip()]
    if not lines:
        return False
    if _DELIBERATION.match(lines[0]):
        return True
    # A bare list of restated rules, with no opener above it.
    bullets = [line for line in lines if line.lstrip().startswith(("-", "*", "•"))]
    return len(bullets) == len(lines) and len(bullets) >= 3


def strip_deliberation(text: str) -> str:
    """Drop a leading block of the model talking about the task.

    Only leading paragraphs are considered, and only until one of them reads
    like an answer — so deliberation-shaped prose later in a genuine reply is
    left alone. If every paragraph looks like deliberation the original is
    returned: an unhelpful answer is recoverable, an empty one is not.
    """
    if not text.strip():
        return text
    paragraphs = re.split(r"\n\s*\n", text)
    kept = 0
    while kept < len(paragraphs) and _is_deliberation(paragraphs[kept]):
        kept += 1
    if kept == 0 or kept == len(paragraphs):
        return text
    return "\n\n".join(paragraphs[kept:]).strip()


class _PreambleFilter:
    """Holds back untagged deliberation from a stream.

    Decides from the first few characters, so an answer that does not open
    with deliberation streams with no delay at all. Once it is holding, it
    releases at the first paragraph that reads like an answer.
    """

    def __init__(self) -> None:
        self.state = "deciding"
        self.held = ""
        # Suppressed paragraphs are kept, not thrown away. A stream cannot be
        # un-sent, so if the whole response turns out to be deliberation there
        # is no second chance to decide it was the answer after all — and an
        # odd answer is recoverable where an empty one is not.
        self.dropped = ""

    def _might_deliberate(self) -> bool:
        """Whether what is held so far could still be a deliberation opener.

        Decided on the first word, which is the whole point: holding every
        answer back for eighty characters to find out would turn a streamed
        reply into one that arrives all at once.
        """
        text = self.held.lstrip()
        if not text:
            return True
        word, sep, _ = text.partition(" ")
        if not sep and "\n" not in text:
            # The first word is still arriving; it may yet become one of them.
            lowered = text.lower().rstrip(":,'")
            return any(w.startswith(lowered) for w in _DELIBERATION_FIRST_WORDS)
        return word.lower().strip(":,.\n'\"") in _DELIBERATION_FIRST_WORDS

    def feed(self, piece: str) -> str:
        if self.state == "passing":
            return piece
        self.held += piece

        if self.state == "deciding":
            if not self._might_deliberate():
                out, self.held, self.state = self.held, "", "passing"
                return out
            if len(self.held) < _PREAMBLE_SAMPLE and "\n" not in self.held:
                return ""
            if not _is_deliberation(self.held):
                out, self.held, self.state = self.held, "", "passing"
                return out
            self.state = "suppressing"

        # Suppressing: release from the first paragraph that is not deliberation.
        while True:
            split = re.search(r"\n\s*\n", self.held)
            if split is None:
                break
            tail = self.held[split.end() :]
            if tail and not _is_deliberation(tail):
                # Only release once there is enough after the break to judge.
                if len(tail) >= _PREAMBLE_SAMPLE or "\n" in tail:
                    self.held, self.state = "", "passing"
                    return tail
                break
            self.dropped += self.held[: split.end()]
            self.held = tail
            if not tail:
                break

        if len(self.held) > _PREAMBLE_CAP:
            out, self.held, self.state = self.held, "", "passing"
            return out
        return ""

    def flush(self) -> str:
        if self.state != "suppressing":
            rest, self.held = self.held, ""
            return rest
        # Nothing in this response ever read as an answer. Hand back
        # everything that was held, rather than nothing at all.
        rest = strip_deliberation(self.dropped + self.held)
        self.held = self.dropped = ""
        return rest


def strip_thinking(text: str) -> str:
    cleaned = _THINK.sub("", text)
    # An unterminated block means the model was cut off mid-deliberation;
    # everything after the opening tag is deliberation, so it goes too.
    opened = cleaned.lower().find(_THINK_OPEN)
    if opened != -1:
        cleaned = cleaned[:opened]
    return cleaned.strip()


class _ThinkFilter:
    """Suppresses thinking from a stream, chunk by chunk.

    A tag can arrive split across chunks ("<thi" then "nk>"), so text is held
    back until it is clear it is not the start of one.
    """

    def __init__(self) -> None:
        self.inside = False
        self.held = ""

    def feed(self, piece: str) -> str:
        self.held += piece
        out: list[str] = []
        while self.held:
            if self.inside:
                end = self.held.lower().find(_THINK_CLOSE)
                if end == -1:
                    # Keep only enough to recognise a closing tag that is
                    # still arriving.
                    self.held = self.held[-len(_THINK_CLOSE) :]
                    return "".join(out)
                self.held = self.held[end + len(_THINK_CLOSE) :]
                self.inside = False
                continue
            start = self.held.lower().find(_THINK_OPEN)
            if start != -1:
                out.append(self.held[:start])
                self.held = self.held[start + len(_THINK_OPEN) :]
                self.inside = True
                continue
            # No tag in hand. Emit everything that cannot be a partial tag.
            safe = len(self.held) - (len(_THINK_OPEN) - 1)
            if safe > 0:
                out.append(self.held[:safe])
                self.held = self.held[safe:]
            return "".join(out)
        return "".join(out)

    def flush(self) -> str:
        rest = "" if self.inside else self.held
        self.held = ""
        return rest


@dataclass
class Discovery:
    """What the daemon reported, or why it could not be asked."""

    reachable: bool
    base_url: str | None = None
    models: list[str] = field(default_factory=list)
    error: str | None = None

    def chat_model(self) -> str | None:
        return _prefer(self.models, CHAT_PREFERENCES, embedding=False)

    def enrichment_model(self) -> str | None:
        """A model that answers directly, for metadata extraction."""
        return _prefer(self.models, ENRICHMENT_PREFERENCES, embedding=False) or self.chat_model()

    def embedding_model(self) -> str | None:
        return _prefer(self.models, EMBEDDING_PREFERENCES, embedding=True)


def _family(name: str) -> str:
    """"llama3.2:3b" and "llama3.2:latest" are the same family."""
    return name.split(":", 1)[0]


def _looks_like_embedder(name: str) -> bool:
    family = _family(name)
    return family in EMBEDDING_PREFERENCES or "embed" in family


def _prefer(models: list[str], preferences: tuple[str, ...], *, embedding: bool) -> str | None:
    for wanted in preferences:
        for installed in models:
            if _family(installed) == wanted:
                return installed
    # Nothing preferred is installed. Fall back to anything of the right
    # kind, so a user with only one unusual model still gets a working
    # feature rather than a configuration error.
    for installed in models:
        if _looks_like_embedder(installed) == embedding:
            return installed
    return None


def candidate_urls() -> list[str]:
    """Where Ollama might be, in order.

    Inside a container `localhost` is the container, not the host, so the
    configured URL alone is not enough — `host.docker.internal` is tried
    next. This is the mistake the compose setup makes by default.
    """
    settings = get_settings()
    configured = settings.ollama_base_url.rstrip("/")
    ordered = [configured, "http://host.docker.internal:11434", "http://localhost:11434"]
    seen: set[str] = set()
    return [url for url in ordered if not (url in seen or seen.add(url))]


_cache: tuple[float, Discovery] | None = None


def discover(*, force: bool = False) -> Discovery:
    """Ask the daemon what it has, trying each candidate URL in turn."""
    global _cache
    now = time.monotonic()
    if not force and _cache is not None and now - _cache[0] < DISCOVERY_TTL_SECONDS:
        return _cache[1]

    last_error: str | None = None
    for base_url in candidate_urls():
        try:
            with urllib.request.urlopen(  # noqa: S310 - fixed http scheme, local daemon
                f"{base_url}/api/tags", timeout=DISCOVERY_TIMEOUT_SECONDS
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = f"{base_url}: {exc}"
            continue

        models = [
            entry["name"]
            for entry in body.get("models", [])
            if isinstance(entry, dict) and isinstance(entry.get("name"), str)
        ]
        found = Discovery(reachable=True, base_url=base_url, models=sorted(models))
        _cache = (now, found)
        return found

    missing = Discovery(
        reachable=False,
        error=(
            "No Ollama daemon answered on "
            + ", ".join(candidate_urls())
            + ". Start it with `ollama serve`."
        ),
    )
    _cache = (now, missing)
    if last_error:
        record("ollama.discover", model=None, duration_ms=0, detail=last_error)
    return missing


def reset_discovery() -> None:
    """Drop the cached probe. Used by tests and after a model is pulled."""
    global _cache
    _cache = None


@dataclass
class Generation:
    """A completed generation and what it cost."""

    text: str
    model: str
    duration_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None


def generate_stream(
    base_url: str,
    model: str,
    prompt: str,
    *,
    operation: str = "ollama.generate",
    fmt: str | None = None,
    system: str | None = None,
    timeout: float = GENERATE_TIMEOUT_SECONDS,
) -> Iterator[str | Generation]:
    """Stream a generation: each text piece as it arrives, then a summary.

    Streaming is the daemon's own default, and the reason the chat can show
    words as they arrive rather than a spinner for ten seconds. The final
    item carries Ollama's own token counts, which is where Telemetry's
    numbers come from — measured by the daemon, not estimated here.
    """
    body: dict = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        # Deterministic: the same question over the same library should
        # answer the same way.
        "options": {"temperature": 0},
        # Reasoning models otherwise spend their budget deliberating in
        # <think> tags. Ignored by daemons and models that do not know it.
        "think": False,
    }
    # Instructions belong in the system role, not in the prompt body. A model
    # given its rules as prose inside the prompt treats them as material to
    # work with, and a reasoning model summarises them back before answering
    # — which is exactly how the rulebook ended up on screen.
    if system:
        body["system"] = system
    if fmt:
        body["format"] = fmt
    payload = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - fixed http scheme, local daemon
        f"{base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    started = time.perf_counter()
    execution_id = uuid.uuid4().hex[:8]
    # A 4B model on a laptop takes seconds to a minute. Emitting the start
    # means Telemetry shows the call in flight rather than nothing at all
    # until it returns.
    record(
        operation,
        model=model,
        duration_ms=0,
        status="STARTED",
        execution_id=execution_id,
    )
    collected: list[str] = []
    filter_ = _ThinkFilter()
    # Chained after it, and only for prose: a JSON reply opens with "{", which
    # never reads as deliberation, but skipping it outright keeps a structured
    # response off a heuristic's path entirely.
    preamble = None if fmt else _PreambleFilter()
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for line in response:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    # A partial line is not an error worth ending a stream
                    # for; the daemon sends one JSON object per line.
                    continue
                piece = event.get("response")
                if isinstance(piece, str) and piece:
                    visible = filter_.feed(piece)
                    if visible and preamble is not None:
                        visible = preamble.feed(visible)
                    if visible:
                        collected.append(visible)
                        yield visible
                if event.get("done"):
                    prompt_tokens = event.get("prompt_eval_count")
                    completion_tokens = event.get("eval_count")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        record(
            operation,
            model=model,
            duration_ms=int((time.perf_counter() - started) * 1000),
            detail=f"unreachable: {exc}",
            status="FAILED",
            execution_id=execution_id,
        )
        raise OllamaUnavailable(
            f"Could not reach the local model '{model}' at {base_url}."
        ) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    trailing = filter_.flush()
    if preamble is not None:
        # Whatever the think filter still held goes through the preamble
        # filter too, then the preamble filter's own remainder.
        trailing = (preamble.feed(trailing) if trailing else "") + preamble.flush()
    if trailing:
        collected.append(trailing)
        yield trailing
    text = strip_thinking("".join(collected))
    record(
        operation,
        model=model,
        duration_ms=duration_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        execution_id=execution_id,
    )
    if not text:
        raise OllamaUnavailable(f"The local model '{model}' returned nothing.")
    yield Generation(
        text=text,
        model=model,
        duration_ms=duration_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


class OllamaUnavailable(RuntimeError):
    """The local daemon or model could not be used. Never a cloud fallback."""


def generate(
    base_url: str,
    model: str,
    prompt: str,
    *,
    operation: str = "ollama.generate",
    fmt: str | None = None,
    system: str | None = None,
    timeout: float = GENERATE_TIMEOUT_SECONDS,
) -> Generation:
    """The whole generation at once, for callers that cannot stream.

    `timeout` is per call. A caller making several in one request — enrichment
    reads a long document in windows — should pass something well under its
    own budget, because the default here is a long-tail guard for a single
    answer rather than a sensible share of a multi-call request.
    """
    final: Generation | None = None
    for item in generate_stream(
        base_url,
        model,
        prompt,
        operation=operation,
        fmt=fmt,
        system=system,
        timeout=timeout,
    ):
        if isinstance(item, Generation):
            final = item
    if final is None:
        raise OllamaUnavailable(f"The local model '{model}' returned nothing.")
    return final
