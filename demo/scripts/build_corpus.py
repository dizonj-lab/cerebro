"""Generate the demo's documents (real PDF and DOCX files) and the knowledge model the web app reads.

    python3 demo/scripts/build_corpus.py        # needs reportlab and python-docx

Writes demo/public/files/*.pdf|docx and demo/src/data/corpus.json. The pipeline is deterministic: fragments are the
paragraphs of each document with their page (PDF) or paragraph number (DOCX); concepts and entities come from a fixed
keyword dictionary; authored links carry the sentence that states them; "similar to" links come from TF-IDF cosine
similarity between documents. Re-running produces the same output.
"""
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor
from reportlab import rl_config
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from corpus import ARTIFACTS, CONCEPTS, ENTITIES, LINKS, OWNER

rl_config.invariant = 1   # no creation timestamps in PDFs, so checksums are reproducible
ROOT = Path(__file__).resolve().parents[1]
FILES, DATA = ROOT / "public" / "files", ROOT / "src" / "data"
MIN_COS = 0.06   # documents are short, so cosine values are modest
NOTE = "Illustrative sample document for the CEREBRO demo."
INK, MUTED, ACCENT = HexColor("#14171c"), HexColor("#5b6472"), HexColor("#2a5d9f")


def slug(a):
    return re.sub(r"[^a-z0-9]+", "-", a["short"].lower()).strip("-")


class TrackedParagraph(Paragraph):
    """Records the page it is drawn on, so fragments can cite a page number."""
    def __init__(self, text, style, sink=None, key=None):
        super().__init__(text, style)
        self.sink, self.key = sink, key

    def draw(self):
        if self.sink is not None:
            self.sink[self.key] = self.canv.getPageNumber()
        super().draw()


def write_pdf(a, path):
    pages = {}
    st = dict(
        title=ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=20, leading=25, textColor=INK, spaceAfter=6),
        meta=ParagraphStyle("m", fontName="Helvetica", fontSize=9.5, leading=13, textColor=MUTED, spaceAfter=14),
        h=ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=ACCENT, spaceBefore=12, spaceAfter=5),
        p=ParagraphStyle("p", fontName="Helvetica", fontSize=11, leading=16.5, textColor=INK, spaceAfter=8),
    )
    story = [Paragraph(a["title"], st["title"]),
             Paragraph(f"{a['kind']} · {a['project']} · {', '.join(a['authors'])} · {a['date']}", st["meta"]),
             TrackedParagraph(f"<i>{a['summary']}</i>", st["p"], pages, (-1, 0)), Spacer(1, 4)]
    for si, (head, paras) in enumerate(a["sections"]):
        story.append(Paragraph(head, st["h"]))
        story += [TrackedParagraph(p, st["p"], pages, (si, pi)) for pi, p in enumerate(paras)]
        if a["id"] in ("ART-0003", "ART-0006", "ART-0012") and si == 1:
            story.append(Spacer(1, 330))   # longer reports run onto a second page
    def footer(c, d):
        c.saveState(); c.setFont("Helvetica", 8); c.setFillColor(MUTED)
        c.drawString(20 * mm, 12 * mm, f"{a['id']} · {NOTE}"); c.drawRightString(190 * mm, 12 * mm, f"Page {d.page}")
        c.restoreState()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=22 * mm,
                            title=a["title"], author=", ".join(a["authors"]), subject=a["summary"], creator="CEREBRO demo corpus")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return pages, max(pages.values())


def write_docx(a, path):
    d = Document()
    d.core_properties.title, d.core_properties.author, d.core_properties.subject = a["title"], ", ".join(a["authors"]), a["summary"]
    d.core_properties.created = d.core_properties.modified = datetime.fromisoformat(a["date"] + "T09:00:00")
    d.core_properties.revision, d.core_properties.last_modified_by = 1, a["authors"][0]
    d.styles["Normal"].font.name, d.styles["Normal"].font.size = "Calibri", Pt(11)
    d.add_heading(a["title"], 0)
    meta = d.add_paragraph(f"{a['kind']} · {a['project']} · {', '.join(a['authors'])} · {a['date']}")
    meta.runs[0].font.color.rgb = RGBColor(0x5B, 0x64, 0x72)
    paras, n = {}, 2
    d.add_paragraph(a["summary"]).runs[0].italic = True
    n += 1; paras[(-1, 0)] = n
    for si, (head, ps) in enumerate(a["sections"]):
        d.add_heading(head, 1); n += 1
        for pi, p in enumerate(ps):
            d.add_paragraph(p); n += 1; paras[(si, pi)] = n
    foot = d.add_paragraph(f"{a['id']} · {NOTE}"); foot.runs[0].font.size = Pt(8)
    d.save(str(path))
    return paras


def tags(text):
    t = text.lower()
    hit = lambda kws: any(re.search(r"\b" + re.escape(k), t) for k in kws)   # word start, so "rag" never matches "fragment"
    concepts = [c for c, kws in CONCEPTS.items() if hit(kws)]
    ents = [e for e, (_, kws) in ENTITIES.items() if hit(kws)]
    return concepts, ents


STOP = set("a an and are as at be by for from has have in into is it its of on or that the their this to was were which with will "
           "each every not no so than then they them can may must should also only one two our we us".split())


def tokens(text):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9\-]+", text.lower()) if w not in STOP and len(w) > 2]


def main():
    FILES.mkdir(parents=True, exist_ok=True); DATA.mkdir(parents=True, exist_ok=True)
    arts, frags = [], []
    for a in ARTIFACTS:
        name = f"{a['id']}-{slug(a)}.{a['type']}"
        path = FILES / name
        if a["type"] == "pdf":
            loc, npages = write_pdf(a, path)
        else:
            loc, npages = write_docx(a, path), None
        blob = path.read_bytes()
        items = [((-1, 0), "Summary", a["summary"])] + [((si, pi), h, p) for si, (h, ps) in enumerate(a["sections"]) for pi, p in enumerate(ps)]
        mine = []
        for k, (key, section, text) in enumerate(items):
            c, e = tags(text)
            where = {"page": loc[key]} if a["type"] == "pdf" else {"paragraph": loc[key]}
            mine.append(dict(id=f"{a['id']}-F{k + 1:02d}", artifact_id=a["id"], section=section, text=text, location=where, concepts=c, entities=e))
        frags += mine
        cc = Counter(c for f in mine for c in f["concepts"]); ec = Counter(x for f in mine for x in f["entities"])
        t0 = datetime.fromisoformat(a["date"] + "T09:00:00")
        steps = [("Uploaded", 0, f"{name} · {len(blob) / 1024:.0f} KB"),
                 ("File inspected", 1, f"SHA-256 {hashlib.sha256(blob).hexdigest()[:12]}… · " + (f"{npages} page(s)" if npages else "Word document")),
                 ("Metadata extracted", 2, "Title, author, date and headings read from the file"),
                 ("AI enrichment", 4, "Local model suggested topics: " + ", ".join(c for c, _ in cc.most_common(3))),
                 ("Human review", 30, f"Approved by {OWNER}"),
                 ("Registered", 31, f"{a['id']} registered"),
                 ("Fragmented", 32, f"{len(mine)} knowledge fragments, deterministic segmentation")]
        arts.append(dict({k: a[k] for k in ("id", "type", "title", "short", "date", "kind", "project", "authors", "summary")},
                         file=f"files/{name}", size_bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(), pages=npages,
                         concepts=[c for c, _ in cc.most_common()], entities=[x for x, _ in ec.most_common()], fragment_count=len(mine),
                         pipeline=[dict(step=s, at=(t0 + timedelta(minutes=m)).isoformat(), detail=d) for s, m, d in steps]))

    by_id = {a["id"]: a for a in ARTIFACTS}
    links = []
    for s, t, kind in LINKS:
        needle = by_id[t]["short"].lower()
        ev = next((f for f in frags if f["artifact_id"] == s and needle in f["text"].lower()), None)
        assert ev, f"{s} never mentions {by_id[t]['short']!r}"
        links.append(dict(source=s, target=t, type=kind, origin="authored", evidence=ev["id"]))

    # semantic links: TF-IDF cosine between whole documents, for pairs not already linked
    docs = {a["id"]: tokens(" ".join(f["text"] for f in frags if f["artifact_id"] == a["id"])) for a in arts}
    df = Counter(w for ws in docs.values() for w in set(ws))
    vec = {i: {w: (1 + math.log(n)) * math.log(len(docs) / df[w]) for w, n in Counter(ws).items()} for i, ws in docs.items()}
    norm = {i: math.sqrt(sum(v * v for v in x.values())) for i, x in vec.items()}
    linked = {frozenset((l["source"], l["target"])) for l in links}
    concepts_of = {a["id"]: set(a["concepts"]) for a in arts}
    pairs = []
    ids = list(docs)
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            if frozenset((x, y)) in linked:
                continue
            cos = sum(v * vec[y].get(w, 0) for w, v in vec[x].items()) / (norm[x] * norm[y])
            pairs.append((cos, x, y))
    pairs.sort(reverse=True)
    per = Counter()
    for cos, x, y in pairs:
        if cos < MIN_COS or per[x] >= 2 or per[y] >= 2:
            continue
        per[x] += 1; per[y] += 1
        links.append(dict(source=x, target=y, type="similar to", origin="semantic", score=round(cos, 3),
                          shared=sorted(concepts_of[x] & concepts_of[y])))

    concepts = [dict(name=c, artifacts=sorted({f["artifact_id"] for f in frags if c in f["concepts"]}),
                     fragments=sum(c in f["concepts"] for f in frags)) for c in CONCEPTS]
    entities = [dict(name=e, kind=k, artifacts=sorted({f["artifact_id"] for f in frags if e in f["entities"]})) for e, (k, _) in ENTITIES.items()]
    out = dict(generated_by="demo/scripts/build_corpus.py", note=NOTE, owner=OWNER, artifacts=arts, fragments=frags, links=links,
               concepts=[c for c in concepts if c["artifacts"]], entities=[e for e in entities if e["artifacts"]])
    (DATA / "corpus.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    sem = [l for l in links if l["origin"] == "semantic"]
    print(f"{len(arts)} artifacts ({sum(a['type'] == 'pdf' for a in arts)} PDF), {len(frags)} fragments, "
          f"{len(links) - len(sem)} authored + {len(sem)} semantic links, {len(out['concepts'])} concepts, {len(out['entities'])} entities")
    for l in sem:
        print("  similar", l["source"], l["target"], l["score"], l["shared"][:4])


if __name__ == "__main__":
    main()
