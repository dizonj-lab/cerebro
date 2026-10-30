#!/usr/bin/env python3
"""Seed a CEREBRO account with a dense, entirely fictional demo library.

Why this exists: demonstrating recall needs a library big enough that recall
is *hard* — one where the answer genuinely spans documents nobody could hold
in their head. Building that by hand costs an afternoon of uploading.

Everything here is invented. The institution, the faculty, the modules and
every word of every document are fiction, written so that no real person's
material goes into a demonstration.

**It drives the real API.** Documents are generated as real PDF, PPTX, DOCX
and Markdown files, uploaded through `/api/artifacts`, reviewed and approved
exactly as a person would. Nothing is written into the database behind the
application's back, so checksums, provenance, fragments, embeddings and the
approval gate are all genuine — the demo shows the real system, not a mock
of it.

Usage:

    python scripts/seed_demo.py --base-url http://localhost:3100

Add --dry-run to write the documents to a folder and upload nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import random
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# --- the fiction -----------------------------------------------------------

INSTITUTION = "Northgate Institute of Technology"
PROGRAMME = "MSc Intelligent Systems"

FACULTY = [
    "Dr. A. Mercer",
    "Prof. L. Okonkwo",
    "Dr. S. Raman",
    "Dr. H. Lindqvist",
    "Prof. M. Debarre",
    "Dr. K. Nakamura",
]

# A controlled vocabulary. The Galaxy draws an edge when two topics appear in
# the same registered document, so the overlap between modules below is what
# makes the graph interesting rather than a set of disconnected islands.
TOPICS = {
    "Consensus": [
        "Consensus requires a majority of nodes to agree before a value is committed.",
        "A leader election round precedes every term in which consensus can be reached.",
        "Consensus protocols trade latency for certainty: nothing commits until a quorum answers.",
    ],
    "Quorum": [
        "A quorum is any subset large enough that two quorums must intersect.",
        "Read and write quorums must overlap for a read to observe the latest write.",
        "Sizing a quorum is a decision about how many failures the system should survive.",
    ],
    "Replication": [
        "Replication keeps copies of the same state on several nodes.",
        "Synchronous replication blocks the writer until replicas acknowledge.",
        "Asynchronous replication accepts a window in which replicas disagree.",
    ],
    "Consistency": [
        "Strong consistency means every read observes the most recent write.",
        "Eventual consistency promises convergence without saying when.",
        "Consistency guarantees are a contract between the store and the reader.",
    ],
    "Partition tolerance": [
        "A network partition splits the cluster into groups that cannot reach each other.",
        "Partition tolerance is not optional in a system that spans a network.",
        "Under partition the system must choose between answering and being correct.",
    ],
    "Fault tolerance": [
        "Fault tolerance is the property of continuing to serve while components fail.",
        "A fault-tolerant design assumes failure is ordinary rather than exceptional.",
        "Redundancy without failure detection does not deliver fault tolerance.",
    ],
    "Vector search": [
        "Vector search ranks documents by distance in an embedding space.",
        "Cosine similarity compares direction rather than magnitude between vectors.",
        "A vector search returns neighbours, which is not the same as returning answers.",
    ],
    "Embeddings": [
        "Embeddings map text into a space where nearby points mean similar things.",
        "An embedding model has a fixed context, and text beyond it cannot be encoded.",
        "Two embeddings are only comparable when produced by the same model.",
    ],
    "Ranking": [
        "Ranking decides which of many plausible results a reader sees first.",
        "Reciprocal rank fusion combines rankings without needing comparable scores.",
        "A ranking function encodes an opinion about what relevance means.",
    ],
    "Relevance": [
        "Relevance is judged against an information need, not against a query string.",
        "Precision and recall pull against each other at every threshold.",
        "A relevance judgement is an opinion recorded by a person.",
    ],
    "Indexing": [
        "An inverted index maps each term to the documents containing it.",
        "Indexing decisions determine which queries can be answered quickly.",
        "An index is a cache of a decision made at write time.",
    ],
    "Knowledge graphs": [
        "A knowledge graph records entities and the relationships between them.",
        "An edge in a knowledge graph should be able to name its evidence.",
        "Graphs make structure visible that a list of documents hides.",
    ],
    "Ontology": [
        "An ontology fixes what the terms in a domain are allowed to mean.",
        "Ontological commitments constrain what can later be inferred.",
        "Two systems disagree most often because their ontologies differ.",
    ],
    "Inference": [
        "Inference derives statements that were not asserted directly.",
        "An inference is only as sound as the assumptions beneath it.",
        "Unchecked inference turns a knowledge base into a rumour mill.",
    ],
    "Provenance": [
        "Provenance records where a value came from and who established it.",
        "Without provenance, a derived fact is indistinguishable from an asserted one.",
        "Provenance is what makes a claim checkable later.",
    ],
    "Retrieval augmentation": [
        "Retrieval augmentation grounds a generated answer in retrieved passages.",
        "The retrieval step decides what the generation step is able to say.",
        "An augmented answer should cite the passages that supported it.",
    ],
    "Evaluation": [
        "Evaluation needs a gold set established before the system is tuned.",
        "A benchmark chosen after the fact measures the choice, not the system.",
        "Evaluation without error analysis reports a number and teaches nothing.",
    ],
    "Chunking": [
        "Chunking splits a document into segments small enough to embed.",
        "A chunk that crosses a page boundary loses the ability to cite precisely.",
        "Chunk size trades retrieval precision against surrounding context.",
    ],
    "Latency": [
        "Latency is what a user experiences; throughput is what a system reports.",
        "Tail latency, not the median, determines whether a system feels fast.",
        "Every network hop adds latency that no amount of caching removes.",
    ],
    "Scheduling": [
        "Scheduling decides which work runs when resources are contended.",
        "A scheduler with no notion of priority starves the work that matters.",
        "Backpressure is a scheduling decision made under load.",
    ],
    "Caching": [
        "A cache trades memory for latency and correctness for speed.",
        "Cache invalidation is hard because it is a consistency problem in disguise.",
        "A cache hit rate means nothing without the cost of a miss.",
    ],
    "Observability": [
        "Observability is the ability to ask new questions of a running system.",
        "Metrics summarise; traces explain. Both are needed.",
        "A system without observability is debugged by guessing.",
    ],
}

TECHNOLOGIES = ["PostgreSQL", "Raft", "Paxos", "Kubernetes", "Redis", "Elasticsearch"]

# Research groups, assigned per module rather than per document. The first
# version put the institution on all 55 documents, which made it a hub joined
# to every topic in the Galaxy — an edge that is true of everything says
# nothing, and it crowded out the links worth clicking.
GROUPS = {
    "Distributed Systems": "Northgate Systems Lab",
    "Information Retrieval": "Meridian Retrieval Group",
    "Machine Reasoning": "Cognitive Systems Unit",
    "Knowledge Representation": "Cognitive Systems Unit",
    "Systems Engineering": "Northgate Systems Lab",
    "Capstone": "Meridian Retrieval Group",
}


@dataclass
class DocSpec:
    title: str
    module: str
    kind: str  # deck | paper | lab | report | note
    author: str
    date: dt.date
    topics: list[str]
    technologies: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)


MODULES: dict[str, dict] = {
    "Distributed Systems": {
        "semester": 1,
        "topics": ["Consensus", "Quorum", "Replication", "Consistency",
                   "Partition tolerance", "Fault tolerance"],
        "tech": ["Raft", "Paxos", "PostgreSQL"],
    },
    "Information Retrieval": {
        "semester": 1,
        "topics": ["Vector search", "Embeddings", "Ranking", "Relevance",
                   "Indexing", "Evaluation"],
        "tech": ["Elasticsearch", "PostgreSQL"],
    },
    "Machine Reasoning": {
        "semester": 2,
        "topics": ["Inference", "Evaluation", "Retrieval augmentation",
                   "Embeddings", "Provenance"],
        "tech": ["Redis"],
    },
    "Knowledge Representation": {
        "semester": 2,
        "topics": ["Knowledge graphs", "Ontology", "Inference", "Provenance"],
        "tech": [],
    },
    "Systems Engineering": {
        "semester": 3,
        "topics": ["Latency", "Scheduling", "Caching", "Observability",
                   "Fault tolerance", "Consistency"],
        "tech": ["Kubernetes", "Redis", "PostgreSQL"],
    },
    "Capstone": {
        "semester": 3,
        "topics": ["Retrieval augmentation", "Chunking", "Provenance",
                   "Evaluation", "Vector search", "Knowledge graphs"],
        "tech": ["PostgreSQL", "Kubernetes"],
    },
}

SEMESTER_START = {
    1: dt.date(2031, 1, 13),
    2: dt.date(2031, 8, 18),
    3: dt.date(2032, 1, 12),
}

KIND_EXT = {"deck": "pptx", "paper": "pdf", "lab": "docx", "report": "pdf", "note": "md"}

TITLE_SHAPES = {
    "deck": ["Lecture {n:02d} — {topic}", "Seminar {n:02d}: {topic} in Practice"],
    "paper": ["{topic}: A Survey", "On the Limits of {topic}", "Revisiting {topic}"],
    "lab": ["Lab {n:02d} — {topic} Experiments", "Lab {n:02d}: Measuring {topic}"],
    "report": ["Project Report — {topic}", "Interim Report: {topic} Evaluation"],
    "note": ["Reading Notes — {topic}", "Seminar Notes: {topic}"],
}


def build_corpus(seed: int = 7) -> list[DocSpec]:
    """A fictional 18-month library with deliberate conceptual overlap."""
    rng = random.Random(seed)
    specs: list[DocSpec] = []
    counters: dict[str, int] = {}

    plan = [
        ("Distributed Systems", [("deck", 5), ("paper", 3), ("lab", 2)]),
        ("Information Retrieval", [("deck", 5), ("paper", 3), ("lab", 2)]),
        ("Machine Reasoning", [("deck", 4), ("paper", 3), ("note", 1)]),
        ("Knowledge Representation", [("deck", 4), ("paper", 3), ("note", 1)]),
        ("Systems Engineering", [("deck", 4), ("paper", 3), ("lab", 3)]),
        ("Capstone", [("deck", 2), ("report", 5), ("lab", 2)]),
    ]

    for module, kinds in plan:
        info = MODULES[module]
        start = SEMESTER_START[info["semester"]]
        offset = 0
        for kind, count in kinds:
            for _ in range(count):
                counters[kind] = counters.get(kind, 0) + 1
                n = counters[kind]
                lead = rng.choice(info["topics"])
                # 3–5 topics per document: the lead plus neighbours, some of
                # which belong to other modules. That cross-module overlap is
                # what gives the Galaxy edges worth clicking.
                others = [t for t in info["topics"] if t != lead]
                picked = [lead] + rng.sample(others, k=min(2, len(others)))
                if rng.random() < 0.45:
                    outside = [t for t in TOPICS if t not in info["topics"]]
                    picked.append(rng.choice(outside))
                title = rng.choice(TITLE_SHAPES[kind]).format(n=n, topic=lead)
                offset += rng.randint(3, 11)
                specs.append(
                    DocSpec(
                        title=title,
                        module=module,
                        kind=kind,
                        author=rng.choice(FACULTY),
                        date=start + dt.timedelta(days=offset),
                        topics=picked,
                        technologies=rng.sample(info["tech"], k=min(2, len(info["tech"]))),
                        projects=["Capstone: Adaptive Retrieval"] if module == "Capstone" else [],
                    )
                )
    return specs


# --- prose -----------------------------------------------------------------

# How much text each kind of document carries. A demo library has to be
# *dense* to demonstrate anything: recall is only impressive when the answer
# could not have been held in one person's head, and that needs documents of
# a realistic length rather than a paragraph standing in for a lecture.
LENGTH = {
    "deck": (14, 20, 2),    # sections, max sections, paragraphs each
    "paper": (10, 14, 4),
    "lab": (8, 12, 3),
    "report": (12, 16, 4),
    "note": (5, 8, 2),
}

# Framing sentences, so a document reads like teaching material rather than
# a list of definitions. Each names its topics, which keeps the text
# genuinely about them.
FRAMES = [
    "This section revisits {a} in the light of the previous week's material.",
    "The treatment of {a} here assumes familiarity with {b}.",
    "Exercises on {a} appear at the end of these notes.",
    "A worked example contrasts {a} with {b}.",
    "Students frequently conflate {a} and {b}; the distinction matters.",
    "The reading list covers {a} in considerably more depth.",
    "In the assessment, {a} is examined alongside {b}.",
    "The seminar discussion of {a} raised an objection worth recording.",
    "Where {a} fails, the usual fallback is to reason about {b} instead.",
    "The literature on {a} is not settled, and the disagreement is instructive.",
    "Measurements of {a} in the lab did not match the lecture's account.",
    "An implementation of {a} must decide what it means by {b}.",
]

SECTION_SHAPES = [
    "{topic}", "{topic} in practice", "Understanding {topic}",
    "{topic}: definitions", "Failure modes of {topic}",
    "{topic} and its tradeoffs", "Worked example — {topic}",
    "Common misconceptions about {topic}", "Measuring {topic}",
    "{topic} revisited", "Notes on {topic}", "Discussion — {topic}",
]


def sections(spec: DocSpec, rng: random.Random) -> list[tuple[str, list[str]]]:
    """Section headings and paragraphs, built from the document's topics.

    The topic words appear verbatim and repeatedly, because that is what
    makes the document genuinely retrievable — a demo library that does not
    answer its own questions demonstrates nothing.
    """
    low, high, per_section = LENGTH[spec.kind]
    count = rng.randint(low, high)

    out: list[tuple[str, list[str]]] = []
    intro = (
        f"{spec.title}. {spec.module}, {PROGRAMME}, {INSTITUTION}. "
        f"Prepared by {spec.author}. This material covers "
        f"{_join(spec.topics)}."
    )
    out.append(("Overview", [intro, _paragraph(spec.topics, rng, 5)]))

    shapes = SECTION_SHAPES[:]
    rng.shuffle(shapes)
    for i in range(count):
        topic = spec.topics[i % len(spec.topics)]
        heading = shapes[i % len(shapes)].format(topic=topic)
        paras = [_paragraph([topic] + spec.topics, rng, rng.randint(4, 6))
                 for _ in range(per_section)]
        paras.append(_frame(spec.topics, rng))
        out.append((heading, paras))

    out.append((
        "Summary",
        [
            _paragraph(spec.topics, rng, 5),
            (f"These notes form part of {spec.module} and should be read "
             "alongside the module reading list."),
        ],
    ))
    return out


def _join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _frame(topics: list[str], rng: random.Random) -> str:
    a = rng.choice(topics)
    b = rng.choice([t for t in topics if t != a] or [a])
    return rng.choice(FRAMES).format(a=a.lower(), b=b.lower())


def _paragraph(topics: list[str], rng: random.Random, sentences: int) -> str:
    pool: list[str] = []
    for topic in topics:
        pool.extend(TOPICS[topic])
    rng.shuffle(pool)
    picked = pool[: max(3, sentences)]
    connectors = ["In practice, ", "By contrast, ", "More usefully, ", "", "",
                  "Note that ", "Crucially, ", "As a result, "]
    body = " ".join(rng.choice(connectors) + s for s in picked)
    if rng.random() < 0.5:
        body += " " + _frame(topics, rng)
    return body


# --- file generation -------------------------------------------------------

def render(spec: DocSpec, rng: random.Random, ordinal: int = 0) -> tuple[str, bytes, str]:
    body = sections(spec, rng)
    ext = KIND_EXT[spec.kind]
    # The ordinal keeps filenames unique. Two documents can legitimately share
    # a title - a module revisits a topic - and without it the second silently
    # overwrote the first when written to a folder.
    stem = f"{ordinal:02d}-{_slug(spec.title)}" if ordinal else _slug(spec.title)
    if ext == "pdf":
        return f"{stem}.pdf", _pdf(spec, body), "application/pdf"
    if ext == "pptx":
        return f"{stem}.pptx", _pptx(spec, body), (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
    if ext == "docx":
        return f"{stem}.docx", _docx(spec, body), (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    return f"{stem}.md", _markdown(spec, body).encode("utf-8"), "text/markdown"


def _slug(title: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in title]
    out = "".join(keep)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:70]


def _pdf(spec: DocSpec, body: list[tuple[str, list[str]]]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, title=spec.title, author=spec.author,
        subject=spec.module, creator=INSTITUTION,
    )
    styles = getSampleStyleSheet()
    flow = [Paragraph(spec.title, styles["Title"]),
            Paragraph(f"{spec.author} · {spec.module}", styles["Italic"]),
            Spacer(1, 14)]
    for heading, paras in body:
        flow.append(Paragraph(heading, styles["Heading2"]))
        for p in paras:
            flow.append(Paragraph(p, styles["BodyText"]))
        flow.append(Spacer(1, 8))
    doc.build(flow)
    return buf.getvalue()


def _pptx(spec: DocSpec, body: list[tuple[str, list[str]]]) -> bytes:
    from pptx import Presentation
    from pptx.util import Pt

    prs = Presentation()
    title_slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_slide.shapes.title.text = spec.title
    title_slide.placeholders[1].text = f"{spec.author} · {spec.module}"

    for heading, paras in body:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = heading
        frame = slide.placeholders[1].text_frame
        frame.word_wrap = True
        first = True
        for para in paras:
            for sentence in [s.strip() for s in para.split(". ") if s.strip()]:
                p = frame.paragraphs[0] if first else frame.add_paragraph()
                p.text = sentence.rstrip(".") + "."
                p.font.size = Pt(14)
                first = False
    prs.core_properties.title = spec.title
    prs.core_properties.author = spec.author
    prs.core_properties.subject = spec.module
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _docx(spec: DocSpec, body: list[tuple[str, list[str]]]) -> bytes:
    from docx import Document

    doc = Document()
    doc.core_properties.title = spec.title
    doc.core_properties.author = spec.author
    doc.core_properties.subject = spec.module
    doc.add_heading(spec.title, level=0)
    doc.add_paragraph(f"{spec.author} · {spec.module}")
    for heading, paras in body:
        doc.add_heading(heading, level=1)
        for p in paras:
            doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _markdown(spec: DocSpec, body: list[tuple[str, list[str]]]) -> str:
    lines = [f"# {spec.title}", "", f"_{spec.author} · {spec.module}_", ""]
    for heading, paras in body:
        lines += [f"## {heading}", ""]
        lines += [p + "\n" for p in paras]
    return "\n".join(lines)


# --- the API ---------------------------------------------------------------

class Client:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")
        self.cookie: str | None = None

    def _request(self, method: str, path: str, *, data=None, headers=None):
        req = urllib.request.Request(f"{self.base}{path}", method=method, data=data)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                raw = resp.read().decode("utf-8")
                set_cookie = resp.headers.get("Set-Cookie")
                if set_cookie:
                    self.cookie = set_cookie.split(";")[0]
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from None

    def json(self, method: str, path: str, payload: dict):
        return self._request(
            method, path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )

    def upload(self, name: str, content: bytes, ctype: str):
        boundary = "----cerebroseed"
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'.encode(),
            f"Content-Type: {ctype}\r\n\r\n".encode(),
            content,
            f"\r\n--{boundary}--\r\n".encode(),
        ])
        return self._request(
            "POST", "/api/artifacts", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://localhost:3100")
    ap.add_argument("--email", default="maya.castellanos@northgate.example")
    ap.add_argument("--password", default="distributed-systems-2031")
    ap.add_argument("--name", default="Maya Castellanos")
    ap.add_argument("--limit", type=int, default=0, help="seed only the first N documents")
    ap.add_argument("--dry-run", metavar="DIR", help="write the files here and upload nothing")
    args = ap.parse_args()

    rng = random.Random(11)
    corpus = build_corpus()
    if args.limit:
        corpus = corpus[: args.limit]

    print(f"Corpus: {len(corpus)} documents, {PROGRAMME} at {INSTITUTION}")
    by_kind: dict[str, int] = {}
    for spec in corpus:
        by_kind[spec.kind] = by_kind.get(spec.kind, 0) + 1
    print("  " + ", ".join(f"{v} {k}" for k, v in sorted(by_kind.items())))

    if args.dry_run:
        import pathlib
        out = pathlib.Path(args.dry_run)
        out.mkdir(parents=True, exist_ok=True)
        for i, spec in enumerate(corpus, 1):
            name, content, _ = render(spec, rng, i)
            (out / name).write_bytes(content)
        print(f"Wrote {len(corpus)} files to {out}")
        return 0

    client = Client(args.base_url)
    try:
        client.json("POST", "/api/auth/signup",
                    {"display_name": args.name, "email": args.email, "password": args.password})
        print(f"Created account {args.email}")
    except RuntimeError:
        client.json("POST", "/api/auth/login",
                    {"email": args.email, "password": args.password})
        print(f"Signed in as {args.email}")

    registered = failed = 0
    for i, spec in enumerate(corpus, 1):
        name, content, ctype = render(spec, rng, i)
        try:
            up = client.upload(name, content, ctype)
            artifact_id = up["id"]
            client.json("PATCH", f"/api/artifacts/{artifact_id}", {
                "metadata": {
                    "title": spec.title,
                    "author": spec.author,
                    "created_date": spec.date.isoformat(),
                    "description": f"{spec.module} — {PROGRAMME}",
                    "language": "en",
                    "topics": spec.topics,
                    "people": [spec.author],
                    "organizations": [GROUPS[spec.module]],
                    "projects": spec.projects,
                    "technologies": spec.technologies,
                    "tags": [spec.module, f"Semester {MODULES[spec.module]['semester']}"],
                    "concepts": spec.topics,
                },
                "approve": True,
            })
            registered += 1
            print(f"  [{i:2d}/{len(corpus)}] registered  {name}")
        except RuntimeError as exc:
            failed += 1
            print(f"  [{i:2d}/{len(corpus)}] FAILED      {name}\n      {exc}")

    print(f"\nRegistered {registered}, failed {failed}.")
    print(f"Sign in at {args.base_url} as {args.email}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
