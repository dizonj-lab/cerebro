"""Load the demo library into a running CEREBRO through its own API, then check what it produced.

    python3 seed/seed.py                                    # web origin http://localhost:3100, demo account
    python3 seed/seed.py --base http://localhost:3000
    python3 seed/seed.py --email you@example.com --password '…'   # into your own account

Nothing is written to the database directly. Each file goes through the same path a person takes in the UI:
upload → extraction and enrichment → review → approve. The script plays the reviewer: it confirms the metadata in
corpus.py, every value of which appears in the document itself (build_files.py checks that). Approval then chunks and
embeds the text with whatever embedding model the deployment uses, so Recall and Search work exactly as they would
for any approved document.

Re-running is safe: files already in the library are not uploaded twice, and ones already registered are left alone.
After changing corpus.py, run with --reset to replace the earlier copies (only the demo files are touched).
Standard library only, so it runs from any Python 3.9+.
"""
import argparse
import http.cookiejar
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from corpus import DOCS  # noqa: E402

LIBRARY = Path(__file__).parent / "library"
DEMO_EMAIL = "demo@cerebro-demo.com"
QUESTIONS = [
    "Why is human review mandatory before a document is registered?",
    "How accurate is the food recognition model?",
    "Which local models were chosen for Recall, and why?",
    "Why do embeddings stay in PostgreSQL?",
]


class Api:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None, *, files=None, ok=(200, 201, 207)):
        headers, data = {"Accept": "application/json"}, None
        if files:
            boundary = uuid.uuid4().hex
            name, content = files
            ctype = mimetypes.guess_type(name)[0] or ("text/markdown" if name.endswith(".md") else "application/octet-stream")
            data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
                    f"Content-Type: {ctype}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with self.http.open(req, timeout=600) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                detail = json.loads(raw)
            except ValueError:
                detail = raw.decode(errors="replace")
            if e.code in ok:
                return e.code, detail
            return e.code, detail


def sign_in(api, name, email, password):
    code, _ = api.call("POST", "/api/auth/login", {"email": email, "password": password})
    if code == 200:
        return "signed in"
    code, body = api.call("POST", "/api/auth/signup", {"display_name": name, "email": email, "password": password})
    if code != 201:
        sys.exit(f"Could not sign in or sign up as {email}: {code} {body}")
    return "account created"


def library_by_filename(api):
    code, body = api.call("GET", "/api/artifacts?limit=500")
    if code != 200:
        sys.exit(f"Could not list artefacts: {code} {body}")
    return {a["filename"]: a for a in body["items"]}


def wait_until_read(api, artifact_id, timeout=600):
    """Review needs extraction finished, and any local-model enrichment job settled: a job still running when the
    document is approved could otherwise store its suggestions over what the reviewer confirmed."""
    start = time.time()
    while True:
        code, a = api.call("GET", f"/api/artifacts/{artifact_id}")
        job = (a or {}).get("enrichment_job") or {}
        if code == 200 and a["status"] != "processing" and job.get("status") not in ("queued", "running"):
            return a
        if time.time() - start > timeout:
            sys.exit(f"Artefact {artifact_id} was still being read or enriched after {timeout}s")
        time.sleep(1.5)


def reviewed_metadata(doc):
    """What the reviewer confirms. created_date only where the file itself carries one (Markdown has no metadata)."""
    return {"title": doc["title"], "description": doc["description"], "language": "English",
            "author": doc["author"], "created_date": None if doc["kind"] == "md" else doc["date"],
            "topics": doc["topics"], "people": doc["people"], "organizations": doc["organizations"],
            "projects": doc["projects"], "technologies": doc["technologies"], "tags": doc["tags"], "concepts": []}


def reset(api):
    """Delete this library's files from the account (matched by filename), with their fragments and vectors.
    Anything else in the account is left alone."""
    names = {d["file"] for d in DOCS}
    gone = 0
    for name, a in library_by_filename(api).items():
        if name in names:
            code, _ = api.call("DELETE", f"/api/artifacts/{a['id']}", ok=(204,))
            gone += code == 204
    print(f"  removed {gone} earlier copies of the demo files")


def seed(api):
    existing = library_by_filename(api)
    done = skipped = 0
    for doc in DOCS:
        path = LIBRARY / doc["file"]
        a = existing.get(doc["file"])
        if a and a["status"] == "registered":
            print(f"  = {doc['file']}  already registered")
            skipped += 1
            continue
        if not a:
            code, a = api.call("POST", "/api/artifacts", files=(doc["file"], path.read_bytes()))
            if code != 201:
                print(f"  ! {doc['file']}  upload refused: {code} {a}")
                continue
        a = wait_until_read(api, a["id"])
        drafted = a.get("metadata") or {}
        t0 = time.time()
        code, a = api.call("PATCH", f"/api/artifacts/{a['id']}", {"metadata": reviewed_metadata(doc), "approve": True})
        if code != 200:
            print(f"  ! {doc['file']}  approval refused: {code} {a}")
            continue
        from_doc = [k for k in ("title", "author", "created_date") if drafted.get(k) and drafted.get(k) == reviewed_metadata(doc)[k]]
        print(f"  + {doc['file']:<48} registered in {time.time() - t0:4.1f}s"
              + (f"  (drafted from the file: {', '.join(from_doc)})" if from_doc else ""))
        done += 1
    return done, skipped


def report(api):
    print("\nGalaxy")
    code, g = api.call("GET", "/api/graph")
    if code == 200:
        clusters = [n for n in g["nodes"] if n.get("type") == "cluster"]
        strong = [e for e in g["edges"] if e.get("strong")]
        print(f"  {len(clusters)} topic clusters, {len(g['edges'])} edges ({len(strong)} backed by two or more documents)")
        for e in sorted(strong, key=lambda e: -e["weight"])[:6]:
            print(f"    {e['source'].split(':', 1)[-1]}  —  {e['target'].split(':', 1)[-1]}   {e['confidence']}")
    print("\nTimeline")
    code, t = api.call("GET", "/api/timeline")
    if code == 200:
        events = t.get("events", [])
        print(f"  {len(events)} dated events" + (f", {events[0]['date']} to {events[-1]['date']}" if events else ""))
    print("\nRecall")
    for q in QUESTIONS:
        code, r = api.call("POST", "/api/recall", {"question": q})
        if code != 200:
            print(f"  ? {q}\n    error {code}: {r}")
            continue
        titles = []
        for s in r["sources"]:
            t = s.get("title") or s.get("filename")
            if t not in titles:
                titles.append(t)
        print(f"  ? {q}\n    sources: {'; '.join(titles[:3]) or 'none'}" + (f"\n    answer:  {r['answer'][:220]}" if r.get("answer") else
              f"\n    ({r.get('note') or 'passages only, no model phrased an answer'})"))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--base", default="http://localhost:3100", help="CEREBRO web origin (default http://localhost:3100)")
    p.add_argument("--email", default=DEMO_EMAIL)
    p.add_argument("--password", default="cerebro-demo-2026")
    p.add_argument("--name", default="Joselito Dizon")
    p.add_argument("--report-only", action="store_true", help="skip loading; just check Galaxy, Timeline and Recall")
    p.add_argument("--reset", action="store_true", help="first delete earlier copies of the demo files from this account")
    a = p.parse_args()
    if not LIBRARY.exists():
        sys.exit("seed/library is missing; run python3 seed/build_files.py first")
    api = Api(a.base)
    print(f"CEREBRO at {a.base}: {sign_in(api, a.name, a.email, a.password)} as {a.email}")
    if a.email == DEMO_EMAIL and not a.report_only:
        # The demo account's metadata is confirmed from corpus.py, so model suggestions would only be computed and
        # replaced. They are off while loading, saving a local-model call per upload, and back on afterwards because
        # the same preference lets Recall phrase answers. Your own account's preferences are never changed.
        api.call("PATCH", "/api/preferences", {"ai_suggestions": False})
    if a.reset and not a.report_only:
        reset(api)
    if not a.report_only:
        try:
            done, skipped = seed(api)
        finally:
            if a.email == DEMO_EMAIL:
                api.call("PATCH", "/api/preferences", {"ai_suggestions": True})
        print(f"\n{done} registered, {skipped} already there")
    report(api)


if __name__ == "__main__":
    main()
