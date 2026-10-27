"""The public datasets, and small synthetic stand-ins for a smoke run.

Public benchmarks rather than the owner's library: their labels were made by
other people, before this evaluation existed, so nothing here can be tuned
to agree with itself — and nobody's private documents end up in a report.

* SciFact (BEIR): 5,183 scientific abstracts, 300 test claims with expert
  relevance judgements. Retrieval.
* 20 Newsgroups (by date): about 18,800 posts in 20 topics, split by posting
  date so the test set is later than the training set. Topic classification
  and similarity.
* SQuAD 2.0 dev: questions written against Wikipedia paragraphs, half of
  them deliberately unanswerable from the paragraph. Grounded answering and
  abstention.

The smoke datasets only exercise the code paths; their numbers mean nothing.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import random
import zipfile
from dataclasses import dataclass

from .common import CACHE, SEED, Run, fetch


@dataclass
class Retrieval:
    corpus: dict[str, str]
    queries: dict[str, str]
    qrels: dict[str, dict[str, int]]


@dataclass
class Topics:
    train_text: list[str]
    train_label: list[int]
    test_text: list[str]
    test_label: list[int]
    names: list[str]
    raw_counts: dict


@dataclass
class Squad:
    """Articles of paragraphs, and questions pointing at one paragraph each."""

    articles: list[dict]
    questions: list[dict]


def scifact(run: Run) -> Retrieval:
    try:
        archive = fetch(
            ["https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip"],
            "scifact.zip",
        )
        run.dataset("BEIR SciFact", archive, "https://github.com/beir-cellar/beir", "CC BY-NC 2.0")
        with zipfile.ZipFile(archive) as z:
            corpus_raw = z.read("scifact/corpus.jsonl").decode()
            queries_raw = z.read("scifact/queries.jsonl").decode()
            qrels_raw = z.read("scifact/qrels/test.tsv").decode()
    except RuntimeError:
        base = "https://huggingface.co/datasets/BeIR"
        files = {
            "corpus": fetch(
                [f"{base}/scifact/resolve/main/corpus.jsonl.gz"], "scifact-corpus.jsonl.gz"
            ),
            "queries": fetch(
                [f"{base}/scifact/resolve/main/queries.jsonl.gz"], "scifact-queries.jsonl.gz"
            ),
            "qrels": fetch(
                [f"{base}/scifact-qrels/resolve/main/test.tsv"], "scifact-qrels-test.tsv"
            ),
        }
        for label, path in files.items():
            run.dataset(
                f"BEIR SciFact ({label})", path, "https://huggingface.co/BeIR", "CC BY-NC 2.0"
            )
        corpus_raw = gzip.decompress(files["corpus"].read_bytes()).decode()
        queries_raw = gzip.decompress(files["queries"].read_bytes()).decode()
        qrels_raw = files["qrels"].read_text()

    corpus = {}
    for line in corpus_raw.splitlines():
        row = json.loads(line)
        corpus[row["_id"]] = f"{row.get('title', '')}. {row['text']}".strip(". ")
    qrels: dict[str, dict[str, int]] = {}
    for row in csv.DictReader(io.StringIO(qrels_raw), delimiter="\t"):
        qrels.setdefault(row["query-id"], {})[row["corpus-id"]] = int(row["score"])
    queries = {}
    for line in queries_raw.splitlines():
        row = json.loads(line)
        if row["_id"] in qrels:
            queries[row["_id"]] = row["text"]
    return Retrieval(corpus, queries, qrels)


def newsgroups(run: Run) -> Topics:
    from sklearn.datasets import fetch_20newsgroups

    home = CACHE / "sklearn"
    # Headers, signatures and quoted replies removed: left in, a classifier
    # learns the sender's address and the newsgroup name in the header,
    # which is the leak this dataset is known for.
    train = fetch_20newsgroups(
        data_home=str(home), subset="train", remove=("headers", "footers", "quotes")
    )
    test = fetch_20newsgroups(
        data_home=str(home), subset="test", remove=("headers", "footers", "quotes")
    )
    for archive in home.rglob("*.pkz"):
        run.dataset(
            "20 Newsgroups (bydate)",
            archive,
            "http://qwone.com/~jason/20Newsgroups/",
            "public research use",
        )
    return Topics(
        list(train.data),
        [int(x) for x in train.target],
        list(test.data),
        [int(x) for x in test.target],
        list(train.target_names),
        {"train": len(train.data), "test": len(test.data)},
    )


def squad(run: Run) -> Squad:
    path = fetch(
        ["https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v2.0.json"], "squad-dev-v2.0.json"
    )
    run.dataset(
        "SQuAD 2.0 dev", path, "https://rajpurkar.github.io/SQuAD-explorer/", "CC BY-SA 4.0"
    )
    body = json.loads(path.read_text())
    articles, questions = [], []
    for a, article in enumerate(body["data"]):
        paragraphs = [p["context"] for p in article["paragraphs"]]
        articles.append({"title": article["title"].replace("_", " "), "paragraphs": paragraphs})
        for p, paragraph in enumerate(article["paragraphs"]):
            for qa in paragraph["qas"]:
                questions.append(
                    {
                        "id": qa["id"],
                        "article": a,
                        "paragraph": p,
                        "question": qa["question"],
                        "answerable": not qa.get("is_impossible", False),
                        "answers": sorted({x["text"] for x in qa.get("answers", [])}),
                    }
                )
    return Squad(articles, questions)


# --- Smoke stand-ins ----------------------------------------------------------

_THEMES = {
    "astronomy": "star galaxy orbit telescope planet comet nebula light-year",
    "cooking": "recipe oven flour garlic simmer sauce bake knife",
    "finance": "interest loan equity dividend market bond inflation budget",
    "medicine": "patient dose symptom vaccine clinic diagnosis therapy trial",
    "sailing": "keel mast harbour tide wind anchor hull starboard",
    "music": "chord tempo melody guitar rhythm octave piano concert",
}


def _sentence(rng: random.Random, words: list[str]) -> str:
    return " ".join(rng.choice(words) for _ in range(rng.randint(8, 16))).capitalize() + "."


def smoke_retrieval() -> Retrieval:
    rng = random.Random(SEED)
    corpus, queries, qrels = {}, {}, {}
    for t, (theme, vocab) in enumerate(_THEMES.items()):
        words = vocab.split()
        for d in range(10):
            corpus[f"{theme}-{d}"] = " ".join(
                _sentence(rng, words) for _ in range(rng.randint(3, 12))
            )
        queries[f"q{t}"] = f"{words[0]} {words[1]} {words[2]}"
        qrels[f"q{t}"] = {f"{theme}-{d}": 1 for d in range(3)}
    return Retrieval(corpus, queries, qrels)


def smoke_topics() -> Topics:
    rng = random.Random(SEED)
    names = list(_THEMES)
    common = "the a of and with for this that".split()
    texts, labels = [], []
    for label, vocab in enumerate(_THEMES.values()):
        words = vocab.split() + common * 2
        for _ in range(40):
            texts.append(" ".join(_sentence(rng, words) for _ in range(3)))
            labels.append(label)
    order = list(range(len(texts)))
    rng.shuffle(order)
    cut = int(len(order) * 0.7)
    return Topics(
        [texts[i] for i in order[:cut]],
        [labels[i] for i in order[:cut]],
        [texts[i] for i in order[cut:]],
        [labels[i] for i in order[cut:]],
        names,
        {"train": cut, "test": len(order) - cut},
    )


def smoke_squad() -> Squad:
    rng = random.Random(SEED)
    articles, questions = [], []
    for a, (theme, vocab) in enumerate(_THEMES.items()):
        words = vocab.split()
        paragraphs = [
            f"The {theme} fact number {p} is {words[p % len(words)]}. " + _sentence(rng, words)
            for p in range(7)
        ]
        articles.append({"title": theme.title(), "paragraphs": paragraphs})
        for p in range(2):
            questions.append(
                {
                    "id": f"{theme}-{p}",
                    "article": a,
                    "paragraph": p,
                    "question": f"What is the {theme} fact number {p}?",
                    "answerable": True,
                    "answers": [words[p % len(words)]],
                }
            )
            questions.append(
                {
                    "id": f"{theme}-{p}-x",
                    "article": a,
                    "paragraph": p,
                    "question": f"Who founded the {theme} society?",
                    "answerable": False,
                    "answers": [],
                }
            )
    return Squad(articles, questions)
