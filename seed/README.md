# Demo library

Twenty-two related artefacts (9 PDF, 7 Word, 4 PowerPoint, 2 Markdown) for showing CEREBRO end to end, and a script
that loads them through CEREBRO's own API.

Loaded, they give:

| View | What you see |
|---|---|
| **Galaxy** | 12 topic clusters joined by recurring links: about 90 edges backed by two or more documents. MealSenseAI and CEREBRO are bridged by shared topics (Explainable AI, Local Language Models, Retrieval-Augmented Generation) and entities (Ollama, PostgreSQL) |
| **Timeline** | About 30 events dated by the documents themselves, June to November 2026 |
| **Recall / Search** | Questions such as *"Why do embeddings stay in PostgreSQL?"* answered from the right documents, with page or slide citations |
| **Library** | Authors and creation dates read from each file's own metadata; lecture decks have no author and stay unknown |

The documents are illustrative samples; the only real figures are MealSenseAI's developer-reported EXP-002 results.

## Load it

CEREBRO must be running, for example `make compose-up WEB_PORT=3100`. For the best Recall, run Ollama with the
models the MVP uses, **before** loading, because documents are embedded with whatever model is active at approval:

```bash
ollama pull mxbai-embed-large && ollama pull qwen3
```

Then, from the repository root (any Python 3.9+, no packages needed):

```bash
python3 seed/seed.py --base http://localhost:3100
```

Sign in as **demo@cerebro-demo.com** / **cerebro-demo-2026**. The script prints what the Galaxy, Timeline and Recall
produced, so you can see it worked before opening the browser.

Into your own account instead:

```bash
python3 seed/seed.py --base http://localhost:3100 --email you@example.com --password '…'
```

After editing `corpus.py`, rebuild the files and replace the earlier copies:

```bash
python3 seed/build_files.py      # needs: pip install reportlab python-docx python-pptx pypdf
python3 seed/seed.py --base http://localhost:3100 --reset
```

`--reset` deletes only the demo files (matched by filename) from that account. `--report-only` skips loading and just
prints the checks.

## How it loads

Nothing is written to the database directly. Each file takes the path a person would: upload → extraction and
enrichment → review → **approve**. The script plays the reviewer and confirms the metadata in `corpus.py`.
`build_files.py` refuses to write a file unless every topic and entity it will be confirmed with appears in its text.

For the demo account, AI suggestions are switched off while loading (the confirmed metadata replaces them anyway) and
switched back on afterwards, because the same preference lets Recall phrase answers. Your own account's preferences
are never changed; the script waits for any enrichment job to finish before approving instead.

## Why the data is shaped this way

The Galaxy draws an edge when two confirmed topics share a registered document, and draws it boldly only when two or
more documents share them. A library whose documents each carry their own one-off topics therefore shows islands, not
a galaxy. This corpus uses **one vocabulary of 12 topics**, each appearing in several documents across both projects.

The Timeline reads dates **stated in the text** ("On 12 September 2026 …"), not upload dates. Every document states
when its events happened, and no other number between 1900 and 2099 appears, since any such number reads as a year.

Recall retrieves passages by embedding similarity. If Recall finds little in your own library, check **Settings** (or
`/api/ml/status`): documents embedded under one model are invisible to queries embedded under another, for example
when Ollama was not reachable at upload time. Re-embedding fixes that (`POST /api/ml/embeddings/backfill`).

## Files

```
seed/corpus.py        the 22 documents: text, topics, entities, dates
seed/build_files.py   writes seed/library/* with honest embedded metadata
seed/seed.py          loads the library through the API and reports the result
seed/library/         the generated files (committed, so loading needs no packages)
```
