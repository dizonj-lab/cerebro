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
        base_url, model, prompt, operation=operation, fmt=fmt, timeout=timeout
    ):
        if isinstance(item, Generation):
            final = item
    if final is None:
        raise OllamaUnavailable(f"The local model '{model}' returned nothing.")
    return final
