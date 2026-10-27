"""The measures, written out rather than imported, so each one can be read.

Ranking measures follow the BEIR/TREC definitions; answer measures follow
the SQuAD evaluation script's normalisation. Every summary statistic comes
with a bootstrap interval, because a mean over 300 queries or 500 questions
is an estimate and should say how wide it is.
"""

from __future__ import annotations

import math
import re
import string
from collections import Counter, defaultdict

import numpy as np

# The same constant as backend/app/services/search.py, so the fused ranking
# here is the one the product computes.
RRF_K = 60


# --- Ranking ----------------------------------------------------------------


def ndcg_at(ranked: list[str], relevant: dict[str, int], k: int = 10) -> float:
    gains = [relevant.get(doc, 0) for doc in ranked[:k]]
    dcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sorted(relevant.values(), reverse=True)[:k]
    idcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def recall_at(ranked: list[str], relevant: dict[str, int], k: int) -> float:
    wanted = {doc for doc, grade in relevant.items() if grade > 0}
    return len(wanted & set(ranked[:k])) / len(wanted) if wanted else 0.0


def mrr_at(ranked: list[str], relevant: dict[str, int], k: int = 10) -> float:
    for i, doc in enumerate(ranked[:k]):
        if relevant.get(doc, 0) > 0:
            return 1.0 / (i + 1)
    return 0.0


def rrf(*rankings: list[str], k: int = RRF_K) -> list[str]:
    """Reciprocal Rank Fusion, as backend/app/services/search.py::_fuse does it."""
    scores: dict[str, float] = defaultdict(float)
    for ranked in rankings:
        for rank, doc in enumerate(ranked, start=1):
            scores[doc] += 1.0 / (k + rank)
    return [doc for doc, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def documents_from_fragments(
    ranked_fragments: list[tuple[str, float]], owner: dict[str, str]
) -> list[str]:
    """A document ranks where its best fragment ranks."""
    seen: list[str] = []
    for fragment, _ in ranked_fragments:
        doc = owner[fragment]
        if doc not in seen:
            seen.append(doc)
    return seen


_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class BM25:
    """Okapi BM25 (k1=1.2, b=0.75): a keyword ranker where any term may match."""

    def __init__(self, docs: dict[str, str], k1: float = 1.2, b: float = 0.75) -> None:
        self.ids = list(docs)
        self.k1, self.b = k1, b
        self.tf = [Counter(tokens(docs[i])) for i in self.ids]
        self.length = np.array([sum(c.values()) for c in self.tf], dtype=float)
        self.avg = float(self.length.mean()) if len(self.length) else 0.0
        df: Counter = Counter()
        for counts in self.tf:
            df.update(counts.keys())
        n = len(self.ids)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.postings: dict[str, list[int]] = defaultdict(list)
        for index, counts in enumerate(self.tf):
            for term in counts:
                self.postings[term].append(index)

    def search(self, query: str, top: int = 100) -> list[tuple[str, float]]:
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokens(query)):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for index in self.postings[term]:
                f = self.tf[index][term]
                norm = self.k1 * (1 - self.b + self.b * self.length[index] / self.avg)
                scores[index] += idf * f * (self.k1 + 1) / (f + norm)
        best = sorted(scores.items(), key=lambda kv: -kv[1])[:top]
        return [(self.ids[i], s) for i, s in best]


# --- Answers (SQuAD normalisation) -----------------------------------------


def normalise_answer(text: str) -> str:
    text = text.lower()
    text = "".join(ch for ch in text if ch not in set(string.punctuation))
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return " ".join(text.split())


def answer_f1(prediction: str, gold: str) -> float:
    pred, true = normalise_answer(prediction).split(), normalise_answer(gold).split()
    common = Counter(pred) & Counter(true)
    same = sum(common.values())
    if not pred or not true or not same:
        return 0.0
    precision, recall = same / len(pred), same / len(true)
    return 2 * precision * recall / (precision + recall)


def answer_recall(prediction: str, gold: str) -> float:
    """Share of the gold answer's words that the response contains."""
    pred, true = Counter(normalise_answer(prediction).split()), normalise_answer(gold).split()
    if not true:
        return 0.0
    return sum(min(pred[w], c) for w, c in Counter(true).items()) / len(true)


def contains_answer(prediction: str, gold: str) -> bool:
    """The gold answer appears, word for word, in the response."""
    needle = normalise_answer(gold)
    return bool(needle) and f" {needle} " in f" {normalise_answer(prediction)} "


# --- Classification ---------------------------------------------------------


def expected_calibration_error(
    probs: np.ndarray, labels: np.ndarray, bins: int = 15
) -> tuple[float, list[dict]]:
    """ECE over equal-width confidence bins, with the bins for a reliability chart."""
    confidence = probs.max(axis=1)
    correct = probs.argmax(axis=1) == labels
    edges = np.linspace(0, 1, bins + 1)
    ece, table = 0.0, []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        inside = (confidence > lo) & (confidence <= hi)
        if not inside.any():
            continue
        acc, conf, share = correct[inside].mean(), confidence[inside].mean(), inside.mean()
        ece += share * abs(acc - conf)
        table.append(
            {
                "lo": round(lo, 3),
                "hi": round(hi, 3),
                "accuracy": float(acc),
                "confidence": float(conf),
                "count": int(inside.sum()),
            }
        )
    return float(ece), table


def roc_points(
    scores: np.ndarray, positive: np.ndarray, points: int = 50
) -> tuple[float, list[dict]]:
    """ROC AUC and a thinned curve, for "does a similarity separate these two groups"."""
    from sklearn.metrics import roc_auc_score, roc_curve

    auc = float(roc_auc_score(positive, scores))
    fpr, tpr, thr = roc_curve(positive, scores)
    keep = np.unique(np.linspace(0, len(fpr) - 1, min(points, len(fpr))).astype(int))
    return auc, [
        {"fpr": float(fpr[i]), "tpr": float(tpr[i]), "threshold": float(thr[i])} for i in keep
    ]


def histogram(values: np.ndarray, lo: float, hi: float, bins: int = 40) -> dict:
    counts, edges = np.histogram(values, bins=bins, range=(lo, hi))
    return {"edges": [round(float(e), 4) for e in edges], "counts": counts.tolist()}


# --- Uncertainty ------------------------------------------------------------


def bootstrap(values, statistic=np.mean, n: int = 2000, seed: int = 0) -> dict:
    """The statistic and its 95% percentile-bootstrap interval."""
    data = np.asarray(values, dtype=float)
    if not len(data):
        return {"value": None, "ci95": [None, None], "n": 0}
    rng = np.random.default_rng(seed)
    draws = [statistic(data[rng.integers(0, len(data), len(data))]) for _ in range(n)]
    return {
        "value": float(statistic(data)),
        "ci95": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
        "n": int(len(data)),
    }


def paired_bootstrap(a, b, n: int = 5000, seed: int = 0) -> dict:
    """Mean difference a - b per item, its interval, and how often it reverses sign."""
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    diff = x - y
    rng = np.random.default_rng(seed)
    draws = np.array([diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(n)])
    observed = float(diff.mean())
    p = float(min(1.0, 2 * min((draws <= 0).mean(), (draws >= 0).mean())))
    return {
        "mean_difference": observed,
        "ci95": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
        "p_two_sided": p,
        "n": int(len(diff)),
    }


def bootstrap_classification(y_true, y_pred, n: int = 1000, seed: int = 0, labels=None) -> dict:
    """Accuracy and macro-F1 with 95% intervals, resampling test documents."""
    from sklearn.metrics import f1_score

    t, p = np.asarray(y_true), np.asarray(y_pred)
    rng = np.random.default_rng(seed)
    acc, f1 = [], []
    for _ in range(n):
        idx = rng.integers(0, len(t), len(t))
        acc.append((t[idx] == p[idx]).mean())
        f1.append(f1_score(t[idx], p[idx], labels=labels, average="macro", zero_division=0))
    return {
        "accuracy": {
            "value": float((t == p).mean()),
            "ci95": [float(np.percentile(acc, 2.5)), float(np.percentile(acc, 97.5))],
        },
        "macro_f1": {
            "value": float(f1_score(t, p, labels=labels, average="macro", zero_division=0)),
            "ci95": [float(np.percentile(f1, 2.5)), float(np.percentile(f1, 97.5))],
        },
    }


def percentiles(values) -> dict:
    data = np.asarray([v for v in values if v is not None], dtype=float)
    if not len(data):
        return {}
    return {
        "p50": float(np.percentile(data, 50)),
        "p95": float(np.percentile(data, 95)),
        "mean": float(data.mean()),
        "max": float(data.max()),
        "n": int(len(data)),
    }
