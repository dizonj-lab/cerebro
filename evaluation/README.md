# CEREBRO model evaluation

How well CEREBRO's models do their jobs, measured on public benchmarks with
labels made by other people, on Buddy's GPU, with every result traceable to
the code, model weights and data that produced it.

```bash
cd ~/cerebro && git pull
./evaluation/run.sh                      # the models CEREBRO runs now ("deployed")
MODELS=designed ./evaluation/run.sh      # qwen3 + mxbai-embed-large, in a separate Ollama
```

Each prints its evidence archive at the end. "Designed" starts its own Ollama on
127.0.0.1:11435 with its own volume: CEREBRO adopts any embedding model that
appears in its Ollama, and switching embedder takes the existing library out
of search until it is re-registered, so the designed models are never put
where the live site would see them.

The first run creates `evaluation/.venv` (PyTorch with CUDA 12.8, scikit-learn,
and CEREBRO's backend package) and downloads the datasets into
`~/.cache/cerebro-eval`. Later runs reuse both, and embeddings are cached by
model digest, so a rerun of an unchanged experiment takes minutes.

Nothing touches CEREBRO's database or the uploaded documents. Keyword search
is measured in a throwaway PostgreSQL container that is removed on exit. The
models are the ones Ollama already serves; no cloud service is called.

## What is measured

The evaluation drives the product's own code — the Ollama embedder with its
payload guard and split-and-pool, the hashing fallback, the chunker, the
keyword query, Reciprocal Rank Fusion, and Ask CEREBRO's prompt, system role,
citation guard and abstention check — so it measures CEREBRO, not a
re-implementation of it.

### 1. Retrieval — BEIR SciFact

5,183 scientific abstracts, 300 test claims, expert relevance labels.
Each abstract is chunked as registration chunks it; a document ranks where
its best fragment ranks.

| System | What it is |
|---|---|
| `keyword` | CEREBRO's keyword search: `plainto_tsquery('english')` + `ts_rank` |
| `bm25` | a reference keyword ranker where any word may match |
| `hashing` | the deterministic embedder CEREBRO falls back to |
| `semantic` | the deployed embedding model (mxbai-embed-large) |
| `hybrid` | keyword + semantic by Reciprocal Rank Fusion, k = 60 — the product's search |
| `hybrid_bm25` | bm25 + semantic, the same fusion |

Reports: nDCG@10, Recall@10, Recall@100, MRR@10 with 95% bootstrap
intervals; paired bootstrap tests between systems; queries with no result;
latency per query; a similarity check (ROC AUC and score histograms for
relevant versus irrelevant fragments); fragment length profile.

### 2. Topics — 20 Newsgroups

About 18,800 posts in 20 topics, split by date. The question: how much
subject structure do CEREBRO's representations hold?

- **Data engineering**: headers, signatures and quoted replies removed (the
  known leak in this dataset); empty and duplicate posts dropped; a leakage
  audit removes test posts whose embedding is ≥ 0.95 similar to a training
  post; lengths against the embedding model's payload limit.
- **Similarity**: same-topic versus different-topic cosine similarity
  (histograms, ROC AUC, silhouette); the topic centroid matrix with the
  Galaxy's own edge rule (mean + 1 standard deviation) applied to it.
- **Projection**: PCA of the dense embeddings and truncated SVD — PCA's
  sparse counterpart — of TF-IDF, in 2-D, with explained variance.
- **Classification**, on one train / validation / test split:
  nearest centroid (the Galaxy's rule, no training), k-nearest neighbours,
  logistic regression and random forest on each embedding; logistic
  regression, linear SVM and random forest on TF-IDF (with the forest's most
  important words); a two-layer neural head trained with PyTorch on the GPU
  (training and validation loss and accuracy per epoch, early stopping,
  calibration, checkpoint by SHA-256); and the local language model choosing
  a topic with no training (400 posts).
  Each with accuracy and macro-F1 (95% intervals), per-class precision,
  recall and F1, and a confusion matrix.

The neural head is a candidate component measured here, not something the
product ships: CEREBRO proposes topics from the document's words and a
person approves them.

### 3. Grounded answering — SQuAD 2.0 dev

250 answerable and 250 unanswerable questions. Each gets six passages the
way Ask CEREBRO gives them — the paragraph it was written against plus the
five most similar paragraphs of the same article — and the product's
prompt.

Declining is counted twice: by the product's own check (`_abstained`), and by
a wider published rule (`MISSING` in `grounded.py`), because the product's
check misses common phrasings such as "do not specify".

Reports: whether the reply contains the gold answer; answer-word recall and
SQuAD F1 (a prose reply depresses F1, so it is for comparison only); an
answered/declined × answerable/unanswerable confusion matrix with abstention
precision, recall and F1; citation rate, invalid citations removed, and
whether the cited passage is the one holding the answer; latency and tokens
per second.

Passages are given whole; Ask CEREBRO trims them to 700 characters, which
would cut answers out of long SQuAD paragraphs.

## The evidence folder

```
evidence/<timestamp>/
  manifest.json            CEREBRO commit, model digests, GPU, versions, dataset and file SHA-256s
  run.log                  everything printed, with timings
  summary.json             headline numbers per experiment
  retrieval/               data_profile, summary, per_query
  topics/                  data_profile, similarity, projection, classifiers, confusion,
                           training_curve, forest_top_words, llm_zero_shot, neural_head.pt
  grounded/                summary, answers.jsonl (every question, reply and citation)
```

`run.sh` packs it as `~/cerebro-evidence-<timestamp>.tar.gz` and prints its
SHA-256. The portfolio's charts are drawn from that archive and nothing else.

## Options

`python -m cerebro_eval --help`, e.g. `./evaluation/run.sh --only retrieval,topics`,
`--qa-per-kind 100` for a shorter answering run, `--llm-topics 0` to skip the
language-model labelling, `--chat-model` / `--embed-model` to evaluate a model
other than the one CEREBRO would pick.

## Checking the harness

```bash
cd evaluation && PYTHONPATH=. .venv/bin/python -m pytest -q tests      # the measures, by hand-worked values
python tests/stub_ollama.py 11500 &                                    # a stand-in daemon
PYTHONPATH=. .venv/bin/python -m cerebro_eval --smoke --ollama http://127.0.0.1:11500 --out /tmp/smoke
```

A smoke run uses synthetic data and a stand-in model: it proves the code
runs and measures nothing.

## Datasets and licences

- SciFact (BEIR) — Wadden et al., 2020; CC BY-NC 2.0.
- 20 Newsgroups (bydate) — Lang, 1995; public research use.
- SQuAD 2.0 — Rajpurkar, Jia and Liang, 2018; CC BY-SA 4.0.
