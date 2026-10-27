"""Experiment 1 — Retrieval: does search put the right document near the top?

Each abstract is chunked by the product's chunker and every fragment is
embedded, as registration does; a document ranks where its best fragment
ranks, as the search page does. Compared:

* keyword       — CEREBRO's keyword search: Postgres `plainto_tsquery` + `ts_rank`
* bm25          — a reference keyword ranker in which any term may match
* hashing       — the deterministic embedder CEREBRO falls back to
* semantic      — the deployed Ollama embedding model
* hybrid        — keyword + semantic by Reciprocal Rank Fusion, k=60: the product's search
* hybrid_bm25   — bm25 + semantic by the same fusion, as the alternative

`plainto_tsquery` requires every word of the query to match. A SciFact
claim is a full sentence, so that is a hard test for it — and a fair one,
because people do paste sentences into a search box.
"""

from __future__ import annotations

import time

import numpy as np

from . import metrics
from .common import Run
from .data import Retrieval
from .engines import Embedder, PostgresKeyword, chunk

TOP = 100


def run(run_: Run, data: Retrieval, embedders: dict[str, Embedder], pg_url: str | None) -> dict:
    with run_.timed("retrieval: chunk"):
        fragments, owner, per_doc = {}, {}, []
        for doc_id, text in data.corpus.items():
            pieces = chunk(text)
            per_doc.append(len(pieces))
            for i, piece in enumerate(pieces):
                fragments[f"{doc_id}#{i}"] = piece
                owner[f"{doc_id}#{i}"] = doc_id
        lengths = np.array([len(t) for t in fragments.values()])
        from app.services.artifacts import tokens as token_budget

        estimates = np.array([token_budget.estimate(t) for t in fragments.values()])
        profile = {
            "documents": len(data.corpus),
            "queries": len(data.queries),
            "judged_pairs": sum(len(v) for v in data.qrels.values()),
            "relevant_per_query": metrics.percentiles([len(v) for v in data.qrels.values()]),
            "fragments": len(fragments),
            "fragments_per_document": metrics.percentiles(per_doc),
            "fragment_chars": metrics.percentiles(lengths),
            "fragment_token_estimate": metrics.percentiles(estimates),
            "fragment_chars_histogram": metrics.histogram(
                lengths, 0, max(1, int(lengths.max()) + 1), 30
            ),
            "document_chars": metrics.percentiles([len(t) for t in data.corpus.values()]),
        }
        run_.write("retrieval/data_profile.json", profile)

    ids = list(fragments)
    rankings: dict[str, dict[str, list[str]]] = {}
    latency: dict[str, float] = {}
    returned_nothing: dict[str, int] = {}

    def record(name: str, searcher) -> None:
        started = time.perf_counter()
        rankings[name] = {}
        for qid, query in data.queries.items():
            rankings[name][qid] = metrics.documents_from_fragments(searcher(query), owner)
        latency[name] = (time.perf_counter() - started) * 1000 / max(1, len(data.queries))
        returned_nothing[name] = sum(1 for r in rankings[name].values() if not r)

    if pg_url:
        with run_.timed("retrieval: keyword (postgres)"):
            pg = PostgresKeyword(pg_url)
            pg.load(fragments)
            record("keyword", lambda q: pg.search(q, TOP))
            pg.drop()
    else:
        run_.notes.append(
            "retrieval: no --pg-url, so CEREBRO's Postgres keyword search was not measured"
        )

    with run_.timed("retrieval: bm25"):
        bm25 = metrics.BM25(fragments)
        record("bm25", lambda q: bm25.search(q, TOP))

    vector_space: dict[str, dict] = {}
    for name, embedder in embedders.items():
        with run_.timed(f"retrieval: {name}"):
            matrix = embedder.embed([fragments[i] for i in ids], "scifact-fragments")
            qids = list(data.queries)
            qmatrix = embedder.embed([data.queries[q] for q in qids], "scifact-queries")
            started = time.perf_counter()
            scores = qmatrix @ matrix.T
            rankings[name] = {}
            for row, qid in enumerate(qids):
                top = np.argsort(-scores[row])[:TOP]
                rankings[name][qid] = metrics.documents_from_fragments(
                    [(ids[i], 0.0) for i in top], owner
                )
            latency[name] = (time.perf_counter() - started) * 1000 / max(1, len(qids))
            returned_nothing[name] = 0
            vector_space[name] = similarity_check(scores, qids, ids, owner, data.qrels)

    semantic = "semantic" if "semantic" in rankings else "hashing"
    for name, keyword in (("hybrid", "keyword"), ("hybrid_bm25", "bm25")):
        if keyword in rankings and semantic in rankings:
            rankings[name] = {
                q: metrics.rrf(rankings[keyword][q], rankings[semantic][q]) for q in data.queries
            }
            latency[name] = latency[keyword] + latency[semantic]
            returned_nothing[name] = sum(1 for r in rankings[name].values() if not r)

    per_query, systems = {}, {}
    for name, ranked in rankings.items():
        rows = {}
        for qid in data.queries:
            rel = data.qrels[qid]
            r = ranked[qid]
            rows[qid] = {
                "ndcg@10": metrics.ndcg_at(r, rel, 10),
                "recall@10": metrics.recall_at(r, rel, 10),
                "recall@100": metrics.recall_at(r, rel, 100),
                "mrr@10": metrics.mrr_at(r, rel, 10),
            }
        per_query[name] = rows
        systems[name] = {
            measure: metrics.bootstrap([row[measure] for row in rows.values()])
            for measure in ("ndcg@10", "recall@10", "recall@100", "mrr@10")
        }
        systems[name]["queries_with_no_result"] = returned_nothing[name]
        systems[name]["ms_per_query"] = round(latency[name], 2)

    comparisons = {}
    for a, b in (
        ("hybrid", "semantic"),
        ("hybrid", "keyword"),
        ("hybrid_bm25", "hybrid"),
        ("semantic", "hashing"),
    ):
        if a in per_query and b in per_query:
            comparisons[f"{a} vs {b}"] = metrics.paired_bootstrap(
                [per_query[a][q]["ndcg@10"] for q in data.queries],
                [per_query[b][q]["ndcg@10"] for q in data.queries],
            )

    summary = {
        "systems": systems,
        "paired_ndcg@10": comparisons,
        "vector_similarity": vector_space,
        "fusion": {"method": "reciprocal rank fusion", "k": metrics.RRF_K},
    }
    run_.write("retrieval/summary.json", summary)
    run_.write("retrieval/per_query.json", per_query)
    return summary


def similarity_check(
    scores: np.ndarray,
    qids: list[str],
    ids: list[str],
    owner: dict[str, str],
    qrels: dict[str, dict[str, int]],
) -> dict:
    """Is a relevant fragment more similar to its claim than an irrelevant one — and by how much?

    Every query's best-scoring fragment per document, split into judged
    relevant and the rest. The ROC AUC says how well cosine similarity alone
    separates them; the two histograms show why a fixed "similar enough"
    threshold does or does not work.
    """
    relevant, other = [], []
    doc_index: dict[str, list[int]] = {}
    for i, fid in enumerate(ids):
        doc_index.setdefault(owner[fid], []).append(i)
    rng = np.random.default_rng(0)
    docs = list(doc_index)
    for row, qid in enumerate(qids):
        wanted = {d for d, g in qrels[qid].items() if g > 0}
        for doc in wanted:
            if doc in doc_index:
                relevant.append(float(scores[row, doc_index[doc]].max()))
        for doc in rng.choice(docs, size=min(50, len(docs)), replace=False):
            if doc not in wanted:
                other.append(float(scores[row, doc_index[doc]].max()))
    values = np.array(relevant + other)
    labels = np.array([1] * len(relevant) + [0] * len(other))
    auc, curve = metrics.roc_points(values, labels)
    lo, hi = float(values.min()), float(values.max())
    return {
        "roc_auc": auc,
        "roc": curve,
        "relevant": metrics.histogram(np.array(relevant), lo, hi),
        "not_relevant": metrics.histogram(np.array(other), lo, hi),
        "relevant_mean": float(np.mean(relevant)),
        "not_relevant_mean": float(np.mean(other)),
    }
