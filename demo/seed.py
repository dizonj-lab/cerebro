"""Load the Larkspur demo library into a CEREBRO instance, through its API.

    python3 demo/seed.py http://127.0.0.1:3300

Standard library only. Creates the demo account (or signs in to it), uploads
every file in demo/corpus/files/library, asks the local model for suggestions
when one is available, and then registers each document with the topics and
names a reviewer would confirm. The file in files/live is left for the
recording to upload on camera.

Meant for the throwaway demo instance (demo/docker-compose.demo.yml), never a
library with real documents in it.
"""

from __future__ import annotations

import http.cookiejar
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

EMAIL = "demo@larkspur.example"
PASSWORD = "larkspur-demo-2026"
NAME = "Alex Rivera"
FILES = Path(__file__).resolve().parent / "corpus" / "files" / "library"

# What a reviewer confirms for each document. Everything named here appears in
# the document's own text.
REVIEW = {
    "Founding Strategy Memo": (["Strategy"], ["Maren Okafor", "Daniel Reyes", "Priya Natarajan"], ["Wren", "Harbor"]),
    "Wren Robot Product Specification v1": (["Robotics"], ["Daniel Reyes"], ["Wren", "Harbor"]),
    "Series A Board Deck": (["Finance", "Strategy"], [], ["Wren"]),
    "Information Security Policy": (["Security"], ["Tomas Lindqvist"], ["Harbor"]),
    "Singapore Pilot Report": (["Operations", "Robotics"], ["Priya Natarajan"], ["Wren", "Harbor"]),
    "Employee Handbook": (["People"], ["Aiko Tanaka"], ["Wren"]),
    "Q1 2024 Quarterly Review": (["Finance"], [], ["Wren"]),
    "Route Planner Outage Postmortem": (["Engineering", "Operations"], ["Daniel Reyes"], ["Harbor", "Wren"]),
    "Q3 2024 Quarterly Review": (["Finance"], [], ["Wren 2"]),
    "Sustainability Report 2024": (["Sustainability"], [], ["Wren", "Wren 2"]),
    "Wren 2 Product Specification": (["Robotics"], [], ["Wren 2", "Harbor"]),
    "FreshCart Customer Case Study": (["Customers", "Operations"], [], ["Wren 2"]),
    "Engineering All-Hands Notes": (["Engineering", "People"], ["Daniel Reyes"], ["Harbor"]),
    "Roadmap 2026-2027": (["Strategy"], [], ["Harbor", "Wren 2"]),
}


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def call(self, method: str, path: str, body: dict | None = None, upload: Path | None = None):
        headers, data = {}, None
        if upload is not None:
            boundary = uuid.uuid4().hex
            kind = mimetypes.guess_type(upload.name)[0] or "application/octet-stream"
            if upload.suffix == ".md":
                kind = "text/markdown"
            data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{upload.name}\"\r\n"
                    f"Content-Type: {kind}\r\n\r\n").encode() + upload.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        with self.opener.open(request, timeout=600) as response:
            raw = response.read()
            return json.loads(raw) if raw else None


def main(base: str) -> None:
    api = Api(base)
    try:
        api.call("POST", "/api/auth/signup", {"email": EMAIL, "password": PASSWORD, "display_name": NAME})
        print(f"created {EMAIL}")
    except urllib.error.HTTPError as exc:
        if exc.code not in (400, 409, 422):
            raise
    api.call("POST", "/api/auth/login", {"email": EMAIL, "password": PASSWORD})

    existing = {a.get("title") for a in api.call("GET", "/api/artifacts").get("items", [])}
    for path in sorted(FILES.iterdir()):
        title = path.stem.split(" ", 1)[1]
        if title in existing:
            print(f"already there: {title}")
            continue
        artifact = api.call("POST", "/api/artifacts", upload=path)
        ident = artifact["id"]
        # A large file is read in the background; wait until it has been.
        for _ in range(120):
            if artifact["status"] != "processing":
                break
            time.sleep(1)
            artifact = api.call("GET", f"/api/artifacts/{ident}")
        # Ask the local model for suggestions, if there is one, and wait for them.
        try:
            api.call("POST", f"/api/artifacts/{ident}/suggest")
            for _ in range(300):
                job = api.call("GET", f"/api/artifacts/{ident}").get("enrichment_job") or {}
                if job.get("status") in (None, "done", "failed", "skipped"):
                    break
                time.sleep(2)
        except urllib.error.HTTPError:
            pass
        artifact = api.call("GET", f"/api/artifacts/{ident}")
        topics, people, projects = REVIEW.get(title, ([], [], []))
        metadata = dict(artifact["metadata"])
        metadata["title"] = title
        metadata["topics"] = topics
        metadata["people"] = sorted(set(metadata.get("people") or []) | set(people))
        metadata["projects"] = sorted(set(metadata.get("projects") or []) | set(projects))
        metadata["organizations"] = sorted(set(metadata.get("organizations") or []) | {"Larkspur Logistics"})
        api.call("PATCH", f"/api/artifacts/{ident}", {"metadata": metadata, "approve": True})
        print(f"registered: {title}  [{', '.join(topics)}]")

    print("done — sign in as", EMAIL, "/", PASSWORD)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3300")
