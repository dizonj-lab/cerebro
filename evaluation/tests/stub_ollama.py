"""A stand-in Ollama daemon on a real socket, for the smoke run only.

It answers /api/tags, /api/embed and a streaming /api/generate well enough
for every code path to execute. Its embeddings are hashed words and its
answers are canned, so nothing it produces is a measurement.

    python tests/stub_ollama.py 11500
    STUB_NO_EMBEDDER=1 python tests/stub_ollama.py 11501   # chat model only
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIMS = 64


def vector(text: str) -> list[float]:
    v = [0.0] * DIMS
    for word in re.findall(r"[a-z]+", text.lower()):
        v[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMS] += 1.0  # noqa: S324 - not security
    return v


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _json(self, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path == "/api/tags":
            models = [
                {
                    "name": "qwen3:stub",
                    "digest": "stub-chat",
                    "size": 1,
                    "details": {"family": "qwen3"},
                },
                {
                    "name": "mxbai-embed-large:stub",
                    "digest": "stub-embed",
                    "size": 1,
                    "details": {"family": "bert"},
                },
            ]
            if os.environ.get("STUB_NO_EMBEDDER"):
                models = models[:1]
            self._json({"models": models})

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/embed":
            self._json({"embeddings": [vector(t) for t in body["input"]]})
        elif self.path == "/api/generate":
            prompt = body["prompt"]
            if "Topics:" in prompt:
                topics = re.findall(r"^- (.+)$", prompt, re.MULTILINE)
                reply = topics[len(prompt) % len(topics)]
            elif "founded" in prompt:
                reply = "The passages do not contain that."
            else:
                match = re.search(r"is (\w+)\.", prompt)
                reply = f"It is {match.group(1) if match else 'unknown'} [1], see also [9]."
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for piece in reply.split(" "):
                self.wfile.write(
                    (json.dumps({"response": piece + " ", "done": False}) + "\n").encode()
                )
            self.wfile.write(
                (
                    json.dumps(
                        {"response": "", "done": True, "prompt_eval_count": 50, "eval_count": 9}
                    )
                    + "\n"
                ).encode()
            )


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
