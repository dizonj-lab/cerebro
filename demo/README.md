# CEREBRO — Knowledge Workspace Demo

A runnable, self-contained demo of CEREBRO's planned **Learn · Connect · Reason · Recall** experience, preloaded with
sixteen linked documents (nine PDFs and seven Word files) across two projects, MealSenseAI and CEREBRO itself.

Everything runs in the browser: no backend, no database, no accounts and no external AI service. The documents are
**illustrative samples** written for the demo; the only quoted figures (EXP-002 accuracy) are the developer-reported
values from the MealSenseAI project.

## Run it

You need Node.js 18 or newer.

```bash
cd demo
npm install
npm run dev            # http://localhost:4300
```

Production build, served locally:

```bash
npm run build && npm run preview     # http://localhost:4300
```

With Docker instead of Node:

```bash
docker build -t cerebro-demo . && docker run --rm -p 4300:80 cerebro-demo    # http://localhost:4300
```

The built `dist/` folder is plain static files and can be put on any static host. Open it through a web server
(`npm run preview`, `npx serve dist`, nginx), not by double-clicking `index.html`: browsers block scripts loaded from
`file://`.

## Five-minute tour

1. **Dashboard**: what the twin has learned (16 artifacts, 121 fragments, 34 relationships) and the most connected documents.
2. **Library → Knowledge Pipeline Proof of Concept**: provenance from upload to registration, every relationship with the
   sentence that states it, and the fragments with their paragraph numbers. PDFs open inline with **Preview**.
3. **Connect**: the knowledge graph. Tap *CEREBRO Solution Architecture* to see what extends, evaluates and implements it.
   Turn on **Concepts** or **Entities** to add shared ideas, people, datasets and tools. Hide a project to see the other.
4. **Timeline**: the four projects as lanes; arcs show which document built on which.
5. **Recall**: ask *"Why is human review mandatory?"*. The answer is quoted passages from three documents, each linked
   to its page or paragraph, plus the reasoning trail between those documents. Ask something unrelated and it says
   nothing in your documents answers it.

## How it works

| Stage | In this demo |
|---|---|
| Learn | `scripts/build_corpus.py` writes the PDF and DOCX files (`public/files/`) and segments each into paragraph-level knowledge fragments with page (PDF) or paragraph (DOCX) locations and SHA-256 checksums |
| Connect | Stated relationships (*extends*, *evaluates*, *implements*, *cites*…) are kept only when the source document contains the sentence that states them; *similar to* links come from TF-IDF cosine similarity between documents; concepts and entities come from a fixed keyword dictionary |
| Reason | The graph and timeline are computed from those relationships (d3-force layout) |
| Recall | BM25 keyword ranking over fragments with a small, visible synonym list for query expansion; answers are extractive quotes, so nothing is paraphrased or invented |

The production design replaces these with the components in `docs/ROADMAP.md`: an object store, an AI-assisted
ingestion pipeline with human review, embeddings in a vector store, a graph store and a local LLM for Recall.

## Regenerating the documents

```bash
pip install reportlab python-docx
npm run corpus          # rewrites public/files/* and src/data/corpus.json
```

The corpus text lives in `scripts/corpus.py`. Output is deterministic.

## Layout

```
demo/
  scripts/corpus.py          the sixteen documents and their stated relationships
  scripts/build_corpus.py    generates the files and the knowledge model
  public/files/              the generated PDFs and Word documents
  src/data/corpus.json       artifacts, fragments, links, concepts, entities
  src/data/model.ts          lookups and the Recall ranking
  src/pages/                 Dashboard, Library, Artifact, Connect, Timeline, Recall
```
