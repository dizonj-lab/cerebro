"""CEREBRO's own components, driven directly.

The evaluation calls the product's code rather than a re-implementation of
it: the Ollama embedder with its payload guard and split-and-pool, the
hashing fallback, the structure-aware chunker, the recall prompt, system
role, citation guard and abstention check. Where the product's behaviour
needs PostgreSQL (keyword search), a throwaway database is used with the
same `plainto_tsquery('english', …)` and `ts_rank` the product runs.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path

import numpy as np

from app.services import ollama
from app.services.artifacts import tokens as token_budget
from app.services.artifacts.chunking import DEFAULT_CHUNK_CHARS, chunk_blocks
from app.services.artifacts.extraction.base import Block, SourceLocation
from app.services.embeddings.hashing import HashingEmbedder
from app.services.embeddings.ollama import OllamaEmbedder

from .common import CACHE, Run


class Embedder:
    """One embedding space, with vectors cached on disk by model and text."""

    def __init__(
        self,
        run: Run,
        kind: str,
        *,
        base_url: str | None = None,
        model: str | None = None,
        digest: str | None = None,
    ) -> None:
        self.run = run
        self.kind = kind
        if kind == "hashing":
            self.provider = HashingEmbedder()
            self.model = self.provider.model
            self.key = self.model
        else:
            # The product checks every vector against a configured width, so ask the daemon for it.
            request = urllib.request.Request(
                f"{base_url.rstrip('/')}/api/embed",
                data=json.dumps({"model": model, "input": ["probe"]}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - local daemon
                dims = len(json.loads(response.read())["embeddings"][0])
            self.provider = OllamaEmbedder(base_url=base_url, model=model, dimensions=dims)
            self.model = model
            # The digest pins the exact weights: a re-pulled model gets fresh vectors.
            self.key = f"{model}@{digest or 'unknown'}"
        self.limit = token_budget.payload_limit(self.model)
        self.split_inputs = 0
        self.seconds = 0.0
        self.count = 0

    @property
    def label(self) -> str:
        return f"{self.kind}/{self.model}"

    def embed(self, texts: list[str], name: str) -> np.ndarray:
        digest = hashlib.sha256(("\x1f".join([self.key, *texts])).encode()).hexdigest()[:24]
        cached = CACHE / "vectors" / f"{name}-{digest}.npy"
        # How many inputs the product would have to split, counted either way.
        self.split_inputs += sum(1 for t in texts if token_budget.estimate(t) > self.limit)
        timing = cached.with_suffix(".json")
        if cached.exists():
            self.run.log(f"   {self.label}: {len(texts)} vectors from cache ({name})")
            # Throughput is what it was when these vectors were first made.
            if timing.exists():
                measured = json.loads(timing.read_text())
                self.seconds += measured["seconds"]
                self.count += measured["count"]
            return np.load(cached)
        started = time.perf_counter()
        out: list[list[float]] = []
        step = 128
        for start in range(0, len(texts), step):
            out.extend(self.provider.embed(texts[start : start + step]))
            if (start // step) % 20 == 0:
                self.run.log(
                    f"   {self.label}: {min(start + step, len(texts))}/{len(texts)} ({name})"
                )
        vectors = np.asarray(out, dtype=np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True).clip(min=1e-12)
        self.seconds += time.perf_counter() - started
        self.count += len(texts)
        cached.parent.mkdir(parents=True, exist_ok=True)
        np.save(cached, vectors)
        timing.write_text(
            json.dumps({"seconds": time.perf_counter() - started, "count": len(texts)})
        )
        return vectors

    def describe(self) -> dict:
        return {
            "kind": self.kind,
            "model": self.model,
            "payload_limit_tokens": self.limit,
            "inputs_split_and_pooled": self.split_inputs,
            "texts_embedded": self.count,
            "texts_per_second": round(self.count / self.seconds, 1) if self.seconds else None,
        }


def chunk(text: str) -> list[str]:
    """The product's chunker, on a single block of text."""
    block = Block(text=text, location=SourceLocation(paragraph=0), kind="paragraph")
    return [c.content for c in chunk_blocks([block], chunk_chars=DEFAULT_CHUNK_CHARS)]


class PostgresKeyword:
    """CEREBRO's keyword search: plainto_tsquery('english') and ts_rank, in a scratch table."""

    def __init__(self, url: str, table: str = "cerebro_eval_fragments") -> None:
        from sqlalchemy import create_engine, text

        self.text = text
        self.engine = create_engine(url)
        self.table = table

    def load(self, fragments: dict[str, str]) -> None:
        t = self.text
        with self.engine.begin() as db:
            db.execute(t(f"DROP TABLE IF EXISTS {self.table}"))
            db.execute(
                t(
                    f"CREATE TABLE {self.table} (id text primary key, body text, "
                    f"tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', body)) STORED)"
                )
            )
            rows = [{"id": k, "body": v} for k, v in fragments.items()]
            for start in range(0, len(rows), 2000):
                db.execute(
                    t(f"INSERT INTO {self.table} (id, body) VALUES (:id, :body)"),
                    rows[start : start + 2000],
                )
            db.execute(t(f"CREATE INDEX ON {self.table} USING gin (tsv)"))
            db.execute(t(f"ANALYZE {self.table}"))

    def search(self, query: str, top: int = 100) -> list[tuple[str, float]]:
        sql = self.text(
            f"SELECT id, ts_rank(tsv, q) AS r FROM {self.table}, plainto_tsquery('english', :q) q "
            f"WHERE tsv @@ q ORDER BY r DESC, id LIMIT :top"
        )
        with self.engine.connect() as db:
            return [(row.id, float(row.r)) for row in db.execute(sql, {"q": query, "top": top})]

    def drop(self) -> None:
        with self.engine.begin() as db:
            db.execute(self.text(f"DROP TABLE IF EXISTS {self.table}"))


class LocalModel:
    """The answering model, called exactly as Ask CEREBRO calls it."""

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url
        self.model = model

    def generate(
        self, prompt: str, *, system: str | None = None, fmt: str | None = None
    ) -> ollama.Generation:
        return ollama.generate(
            self.base_url,
            self.model,
            prompt,
            system=system,
            fmt=fmt,
            operation="evaluation",
            timeout=180,
        )


def pick_models(
    base_url: str, installed: list[dict], chat: str | None, embed: str | None
) -> tuple[str | None, str | None]:
    """The models the product would choose itself, unless told otherwise."""
    names = [m["name"] for m in installed]
    found = ollama.Discovery(reachable=True, base_url=base_url, models=names)
    return chat or found.chat_model(), embed or found.embedding_model()


def digest_of(installed: list[dict], name: str | None) -> str | None:
    for m in installed:
        if m["name"] == name or (name and m["name"].split(":")[0] == name.split(":")[0]):
            return m["digest"]
    return None


def save_json_lines(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
