"""Experiment 3 — Grounded answering: does Ask CEREBRO answer from the passages, and only from them?

For each SQuAD 2.0 question, the model is given six passages the way Ask
CEREBRO gives them: the paragraph the question was written against and the
five paragraphs of the same article most similar to it by the deployed
embedding model, shuffled. Half the questions are unanswerable from that
paragraph by design. The prompt, the system role, the citation guard and
the abstention check are the product's own (backend/app/services/recall.py).

Measured:
* answerable questions — does the reply contain the gold answer (exact,
  after SQuAD normalisation); share of the answer's words present; SQuAD F1,
  which a prose reply depresses and is reported for comparison only;
* abstention — a confusion matrix of answered / declined against
  answerable / unanswerable: declining the unanswerable is correct;
* citations — does the reply cite, is every citation real, does it cite the
  paragraph that holds the answer;
* cost — latency and the daemon's own token counts.

One deliberate difference from the product: passages are given whole.
Ask CEREBRO trims each to 700 characters, which would cut answers out of
long SQuAD paragraphs and grade the trimming rather than the model.
"""

from __future__ import annotations

import re

import numpy as np

from app.services import recall

from . import metrics
from .common import SEED, Run
from .data import Squad
from .engines import Embedder, LocalModel, save_json_lines

PASSAGES = 6


def run(run_: Run, data: Squad, embedder: Embedder, llm: LocalModel, per_kind: int) -> dict:
    rng = np.random.default_rng(SEED)
    answerable = [q for q in data.questions if q["answerable"]]
    unanswerable = [q for q in data.questions if not q["answerable"]]
    chosen = [
        answerable[i]
        for i in rng.choice(len(answerable), min(per_kind, len(answerable)), replace=False)
    ]
    chosen += [
        unanswerable[i]
        for i in rng.choice(len(unanswerable), min(per_kind, len(unanswerable)), replace=False)
    ]

    with run_.timed("grounded: embed paragraphs"):
        flat = [
            (a, p) for a, art in enumerate(data.articles) for p in range(len(art["paragraphs"]))
        ]
        index = {key: i for i, key in enumerate(flat)}
        vectors = embedder.embed(
            [data.articles[a]["paragraphs"][p] for a, p in flat], "squad-paragraphs"
        )

    rows = []
    with run_.timed("grounded: answer"):
        for n, q in enumerate(chosen):
            a = q["article"]
            gold = index[(a, q["paragraph"])]
            siblings = [
                index[(a, p)]
                for p in range(len(data.articles[a]["paragraphs"]))
                if p != q["paragraph"]
            ]
            near = sorted(siblings, key=lambda i: -float(vectors[i] @ vectors[gold]))[
                : PASSAGES - 1
            ]
            order = [gold, *near]
            rng.shuffle(order)
            passages = [
                {
                    "index": k + 1,
                    "title": data.articles[a]["title"],
                    "filename": "",
                    "excerpt": data.articles[flat[i][0]]["paragraphs"][flat[i][1]],
                }
                for k, i in enumerate(order)
            ]
            gold_index = order.index(gold) + 1
            generated = llm.generate(recall._prompt(q["question"], passages), system=recall._SYSTEM)
            raw_cites = [int(x) for x in re.findall(r"\[(\d{1,2})\]", generated.text)]
            answer, cited = recall._cite_guard(recall._natural(generated.text), len(passages))
            declined = recall._abstained(answer)
            row = {
                "id": q["id"],
                "question": q["question"],
                "answerable": q["answerable"],
                "gold": q["answers"],
                "answer": answer,
                "declined": declined,
                "cited": cited,
                "gold_passage": gold_index,
                "invalid_citations_removed": sum(
                    1 for c in raw_cites if not 1 <= c <= len(passages)
                ),
                "duration_ms": generated.duration_ms,
                "prompt_tokens": generated.prompt_tokens,
                "completion_tokens": generated.completion_tokens,
            }
            if q["answerable"]:
                row["contains_answer"] = any(
                    metrics.contains_answer(answer, g) for g in q["answers"]
                )
                row["answer_word_recall"] = max(
                    metrics.answer_recall(answer, g) for g in q["answers"]
                )
                row["squad_f1"] = max(metrics.answer_f1(answer, g) for g in q["answers"])
            rows.append(row)
            if n % 25 == 0:
                run_.log(f"   answered {n}/{len(chosen)}")

    (run_.out / "grounded").mkdir(exist_ok=True)
    save_json_lines(run_.out / "grounded" / "answers.jsonl", rows)

    ans = [r for r in rows if r["answerable"]]
    una = [r for r in rows if not r["answerable"]]
    replied = [r for r in ans if not r["declined"]]
    confusion = {
        "answerable_answered": sum(1 for r in ans if not r["declined"]),
        "answerable_declined": sum(1 for r in ans if r["declined"]),
        "unanswerable_answered": sum(1 for r in una if not r["declined"]),
        "unanswerable_declined": sum(1 for r in una if r["declined"]),
    }
    tp, fp = confusion["unanswerable_declined"], confusion["answerable_declined"]
    fn = confusion["unanswerable_answered"]
    precision = tp / (tp + fp) if tp + fp else None
    recall_ = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall_ / (precision + recall_) if precision and recall_ else None
    speeds = [
        r["completion_tokens"] / (r["duration_ms"] / 1000)
        for r in rows
        if r["completion_tokens"] and r["duration_ms"]
    ]
    summary = {
        "model": llm.model,
        "embedding_model": embedder.label,
        "passages_per_question": PASSAGES,
        "questions": {"answerable": len(ans), "unanswerable": len(una)},
        "answerable": {
            "contains_gold_answer": metrics.bootstrap([r["contains_answer"] for r in ans]),
            "contains_gold_answer_when_answered": metrics.bootstrap(
                [r["contains_answer"] for r in replied]
            ),
            "answer_word_recall": metrics.bootstrap([r["answer_word_recall"] for r in ans]),
            "squad_f1": metrics.bootstrap([r["squad_f1"] for r in ans]),
        },
        "abstention": {
            "confusion": confusion,
            "precision": precision,
            "recall": recall_,
            "f1": f1,
            "accuracy": (tp + confusion["answerable_answered"]) / len(rows) if rows else None,
            "answered_unanswerable_rate": fn / len(una) if una else None,
        },
        "citations": {
            "answers_with_a_citation": metrics.bootstrap([bool(r["cited"]) for r in replied]),
            "cites_the_answer_paragraph": metrics.bootstrap(
                [r["gold_passage"] in r["cited"] for r in replied]
            ),
            "replies_with_invalid_citations_removed": sum(
                1 for r in rows if r["invalid_citations_removed"]
            ),
            "citations_per_answer": metrics.percentiles([len(r["cited"]) for r in replied]),
        },
        "cost": {
            "latency_ms": metrics.percentiles([r["duration_ms"] for r in rows]),
            "prompt_tokens": metrics.percentiles([r["prompt_tokens"] for r in rows]),
            "completion_tokens": metrics.percentiles([r["completion_tokens"] for r in rows]),
            "completion_tokens_per_second": metrics.percentiles(speeds),
        },
    }
    run_.write("grounded/summary.json", summary)
    return summary
