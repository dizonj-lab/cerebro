"""Write the demo library's files from corpus.py, with honest embedded metadata.

    python3 seed/build_files.py          # needs reportlab, python-docx, python-pptx, pypdf

Each file carries its own title, author (or none) and creation date, because CEREBRO reads author and creation date
only from a document's own metadata or a printed byline. Before writing anything, every topic and entity a document
will be reviewed with is checked to appear in its text, so nothing the seed confirms is absent from the evidence.
Output is reproducible: fixed timestamps, no random identifiers.
"""
import io
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from docx import Document
from docx.shared import Pt
from pptx import Presentation
from pptx.util import Pt as PPt
from pypdf import PdfReader, PdfWriter
from reportlab import rl_config
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

sys.path.insert(0, str(Path(__file__).parent))
from corpus import DOCS, TOPICS  # noqa: E402

rl_config.invariant = 1
OUT = Path(__file__).parent / "library"
NOTE = "Illustrative sample document for the CEREBRO demo library."
CITED_YEARS: set[str] = set()   # none: a cited year would stretch the Timeline back to it
YEARISH = re.compile(r"\b(19\d{2}|20\d{2})\b")


def when(d):
    return datetime.fromisoformat(d + "T09:00:00").replace(tzinfo=timezone.utc)


def byline(doc):
    """Printed on the first page: the only place besides file metadata an author may come from."""
    return f"Prepared by {doc['author']}" if doc["author"] and doc["kind"] != "pptx" else None


def text_of(doc):
    return " ".join([doc["title"], byline(doc) or ""] + [h + " " + " ".join(ps) for h, ps in doc["body"]])


def check(doc):
    text = text_of(doc).lower()
    for field in ("topics", "projects", "technologies", "organizations", "people"):
        for v in doc[field]:
            assert v.lower() in text, f"{doc['file']}: {field} value {v!r} is not in the text"
    assert all(t in TOPICS for t in doc["topics"]), doc["file"]
    # only dates may look like years, or the Timeline will misplace them: "12 May 2026", "May 2026", or a cited year
    t = text_of(doc)
    dated = {m.end() for m in re.finditer(r"(january|february|march|april|may|june|july|august|september|october|november|december) \d{4}", t, re.I)}
    for m in YEARISH.finditer(t):
        assert m.end() in dated or m.group() in CITED_YEARS, f"{doc['file']}: {t[max(0, m.start() - 20):m.end()]!r} reads as a year"


def pdf(doc, path):
    ink, muted, accent = HexColor("#14171c"), HexColor("#5b6472"), HexColor("#2a5d9f")
    st = dict(t=ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=19, leading=24, textColor=ink, spaceAfter=6),
              m=ParagraphStyle("m", fontName="Helvetica", fontSize=9.5, leading=13, textColor=muted, spaceAfter=14),
              h=ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=accent, spaceBefore=12, spaceAfter=5),
              p=ParagraphStyle("p", fontName="Helvetica", fontSize=11, leading=16.5, textColor=ink, spaceAfter=8))
    story = [Paragraph(doc["title"], st["t"]),
             *([Paragraph(byline(doc), st["m"])] if byline(doc) else []), Paragraph(doc["description"], st["m"])]
    for i, (h, ps) in enumerate(doc["body"]):
        story += [Paragraph(h, st["h"])] + [Paragraph(p, st["p"]) for p in ps]
        if i == 1 and len(doc["body"]) > 3:
            story.append(Spacer(1, 360))   # longer documents run to a second page, so citations show page numbers

    # The note goes last, in the flow. A page footer is drawn before the page's text, so extraction would put it
    # first and every preview and fragment would open with it.
    story.append(Paragraph(NOTE, st["m"]))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=22 * mm).build(story)
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(buf.getvalue())))
    stamp = when(doc["date"]).strftime("D:%Y%m%d%H%M%S+00'00'")
    w.add_metadata({"/Title": doc["title"], "/Author": doc["author"] or "", "/Subject": doc["description"],
                    "/Creator": "CEREBRO demo library", "/Producer": "CEREBRO demo library", "/CreationDate": stamp, "/ModDate": stamp})
    if not doc["author"]:
        del w._info.get_object()["/Author"]
    with open(path, "wb") as f:
        w.write(f)


def docx(doc, path):
    d = Document()
    cp = d.core_properties
    cp.title, cp.subject, cp.author, cp.last_modified_by = doc["title"], doc["description"], doc["author"] or "", doc["author"] or ""
    cp.created = cp.modified = when(doc["date"]).replace(tzinfo=None)
    cp.revision = 1
    d.styles["Normal"].font.name, d.styles["Normal"].font.size = "Calibri", Pt(11)
    d.add_heading(doc["title"], 0)
    if byline(doc):
        d.add_paragraph(byline(doc))
    d.add_paragraph(doc["description"]).runs[0].italic = True
    for h, ps in doc["body"]:
        d.add_heading(h, 1)
        for p in ps:
            d.add_paragraph(p)
    d.add_paragraph(NOTE).runs[0].font.size = Pt(8)
    d.save(str(path))


def pptx(doc, path):
    prs = Presentation()
    cp = prs.core_properties
    cp.title, cp.subject, cp.author, cp.last_modified_by = doc["title"], doc["description"], doc["author"] or "", doc["author"] or ""
    cp.created = cp.modified = when(doc["date"]).replace(tzinfo=None)
    cp.revision = 1
    for i, (h, bullets) in enumerate(doc["body"]):
        s = prs.slides.add_slide(prs.slide_layouts[0 if i == 0 else 1])
        s.shapes.title.text = h
        body = s.placeholders[1].text_frame
        body.text = bullets[0]
        for b in bullets[1:]:
            body.add_paragraph().text = b
        for para in body.paragraphs:
            for r in para.runs:
                r.font.size = PPt(20 if i else 18)
    prs.save(str(path))


def md(doc, path):
    lines = [f"# {doc['title']}", ""] + ([byline(doc), ""] if byline(doc) else []) + [f"_{doc['description']}_", ""]
    for h, ps in doc["body"]:
        lines += [f"## {h}", ""] + [p + "\n" for p in ps]
    lines.append(f"<sub>{NOTE}</sub>\n")
    path.write_text("\n".join(lines))


def main():
    OUT.mkdir(exist_ok=True)
    for doc in DOCS:
        check(doc)
        {"pdf": pdf, "docx": docx, "pptx": pptx, "md": md}[doc["kind"]](doc, OUT / doc["file"])
    kinds = {k: sum(d["kind"] == k for d in DOCS) for k in ("pdf", "docx", "pptx", "md")}
    print(f"{len(DOCS)} files in {OUT}: {kinds}")


if __name__ == "__main__":
    main()
