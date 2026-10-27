"""Experiment 2 — Topics: how well do CEREBRO's representations separate subjects?

CEREBRO groups knowledge by topic: the Galaxy draws topic centroids and
links the ones more alike than the library's typical pair. This experiment
asks how much subject structure the embedding space actually holds, on
20 Newsgroups, whose topic labels were assigned by people.

Data engineering
  Cleaning (headers, signatures, quoted replies removed), empty documents
  dropped, exact duplicates found, near-duplicates across the train/test
  split found by embedding similarity and removed from the test set (the
  leakage audit), lengths measured against the embedding model's limit.

Similarity
  Within-topic versus between-topic cosine similarity; the topic-to-topic
  centroid matrix with the Galaxy's own edge rule applied to it.

Projection
  PCA of the dense embeddings and truncated SVD (the sparse counterpart of
  PCA) of TF-IDF, in two dimensions, with explained variance and silhouette.

Classification
  The same train / validation / test split for every model:
  nearest centroid (the Galaxy's rule, no training), k-nearest neighbours,
  logistic regression, random forest, linear SVM on TF-IDF, a small neural
  head trained with PyTorch on the GPU (loss curves, early stopping,
  checkpoint by SHA-256), and the local language model classifying with no
  training at all.

The neural head is a candidate component measured here, not something the
product ships: CEREBRO proposes topics from the document's own words and a
person approves them.
"""

from __future__ import annotations

import hashlib
import re
import time

import numpy as np

from . import metrics
from .common import SEED, Run, sha256_of
from .data import Topics
from .engines import Embedder, LocalModel

MAX_CHARS = 4000  # the first 4,000 characters of a post are embedded
NEAR_DUPLICATE = 0.95  # cosine at or above this across splits is treated as the same text
PROJECTION_SAMPLE = 1500


def run(
    run_: Run,
    data: Topics,
    embedders: dict[str, Embedder],
    llm: LocalModel | None,
    llm_sample: int,
    epochs: int,
) -> dict:
    from sklearn.model_selection import train_test_split

    names = data.names
    with run_.timed("topics: clean and audit"):
        train_text, train_y, test_text, test_y, audit = clean(data)

    space = "semantic" if "semantic" in embedders else "hashing"
    dense = {}
    with run_.timed("topics: embed"):
        for key, embedder in embedders.items():
            dense[key] = (
                embedder.embed([t[:MAX_CHARS] for t in train_text], f"20ng-train-{key}"),
                embedder.embed([t[:MAX_CHARS] for t in test_text], f"20ng-test-{key}"),
            )

    # Leakage audit: a test post that is (nearly) a training post measures
    # memory, not generalisation.
    tr, te = dense[space]
    best = np.zeros(len(te), dtype=np.float32)
    for start in range(0, len(te), 1024):
        best[start : start + 1024] = (te[start : start + 1024] @ tr.T).max(axis=1)
    leaked = best >= NEAR_DUPLICATE
    audit["near_duplicates_across_split"] = int(leaked.sum())
    audit["near_duplicate_threshold"] = NEAR_DUPLICATE
    audit["test_after_dedup"] = int((~leaked).sum())
    keep = ~leaked
    test_text = [t for t, k in zip(test_text, keep, strict=True) if k]
    test_y = np.asarray(test_y)[keep]
    for key in dense:
        dense[key] = (dense[key][0], dense[key][1][keep])
    train_y = np.asarray(train_y)

    profile = profile_of(train_text, train_y, test_text, test_y, names, embedders[space], audit)
    run_.write("topics/data_profile.json", profile)

    with run_.timed("topics: similarity"):
        run_.write(
            "topics/similarity.json",
            {key: similarity(dense[key][0], train_y, names) for key in dense},
        )

    # One split for everything: 10% of the training posts, stratified, choose
    # hyper-parameters and stop training; the test set is touched once.
    idx = np.arange(len(train_y))
    fit_idx, val_idx = train_test_split(idx, test_size=0.1, stratify=train_y, random_state=SEED)

    with run_.timed("topics: tf-idf"):
        from sklearn.feature_extraction.text import TfidfVectorizer

        tfidf = TfidfVectorizer(
            sublinear_tf=True, min_df=2, max_df=0.5, max_features=30000, stop_words="english"
        )
        sparse_fit = tfidf.fit_transform([train_text[i] for i in fit_idx])
        sparse_val = tfidf.transform([train_text[i] for i in val_idx])
        sparse_test = tfidf.transform(test_text)

    with run_.timed("topics: projection"):
        run_.write(
            "topics/projection.json", projection(dense[space][1], sparse_test, test_y, names)
        )

    results, confusions = {}, {}
    y_fit, y_val = train_y[fit_idx], train_y[val_idx]

    def score(
        name: str, model_desc: str, features: str, predict, seconds: float, probs=None, extra=None
    ):
        from sklearn.metrics import classification_report, confusion_matrix

        pred = np.asarray(predict)
        report = classification_report(
            test_y,
            pred,
            labels=list(range(len(names))),
            target_names=names,
            output_dict=True,
            zero_division=0,
        )
        entry = {
            "model": model_desc,
            "features": features,
            "fit_seconds": round(seconds, 1),
            **metrics.bootstrap_classification(test_y, pred),
            "weighted_f1": report["weighted avg"]["f1-score"],
            "per_class": {
                n: {k: report[n][k] for k in ("precision", "recall", "f1-score", "support")}
                for n in names
            },
        }
        if probs is not None:
            ece, bins = metrics.expected_calibration_error(probs, test_y)
            entry["calibration"] = {"ece": ece, "bins": bins}
        if extra:
            entry.update(extra)
        results[name] = entry
        confusions[name] = confusion_matrix(test_y, pred, labels=list(range(len(names)))).tolist()
        run_.log(
            f"   {name}: accuracy {entry['accuracy']['value']:.3f}, "
            f"macro-F1 {entry['macro_f1']['value']:.3f}"
        )

    for key, (train_vec, test_vec) in dense.items():
        x_fit, x_val = train_vec[fit_idx], train_vec[val_idx]
        label = embedders[key].label
        with run_.timed(f"topics: classical models on {key}"):
            started = time.perf_counter()
            centroids = np.stack([x_fit[y_fit == c].mean(axis=0) for c in range(len(names))])
            centroids /= np.linalg.norm(centroids, axis=1, keepdims=True).clip(min=1e-12)
            score(
                f"nearest_centroid_{key}",
                "nearest topic centroid (cosine) — the Galaxy's rule, no training",
                label,
                (test_vec @ centroids.T).argmax(axis=1),
                time.perf_counter() - started,
            )
            fit_and_score(
                score,
                f"knn_{key}",
                "k-nearest neighbours (cosine)",
                label,
                "knn",
                x_fit,
                y_fit,
                x_val,
                y_val,
                test_vec,
            )
            fit_and_score(
                score,
                f"logreg_{key}",
                "logistic regression",
                label,
                "logreg",
                x_fit,
                y_fit,
                x_val,
                y_val,
                test_vec,
            )
            fit_and_score(
                score,
                f"random_forest_{key}",
                "random forest",
                label,
                "forest",
                x_fit,
                y_fit,
                x_val,
                y_val,
                test_vec,
            )

    with run_.timed("topics: classical models on tf-idf"):
        fit_and_score(
            score,
            "logreg_tfidf",
            "logistic regression",
            "tf-idf (sparse)",
            "logreg",
            sparse_fit,
            y_fit,
            sparse_val,
            y_val,
            sparse_test,
        )
        fit_and_score(
            score,
            "linear_svm_tfidf",
            "linear SVM",
            "tf-idf (sparse)",
            "svm",
            sparse_fit,
            y_fit,
            sparse_val,
            y_val,
            sparse_test,
        )
        forest = fit_and_score(
            score,
            "random_forest_tfidf",
            "random forest",
            "tf-idf (sparse)",
            "forest",
            sparse_fit,
            y_fit,
            sparse_val,
            y_val,
            sparse_test,
        )
        vocabulary = np.array(tfidf.get_feature_names_out())
        order = np.argsort(-forest.feature_importances_)[:25]
        run_.write(
            "topics/forest_top_words.json",
            [
                {"word": str(vocabulary[i]), "importance": float(forest.feature_importances_[i])}
                for i in order
            ],
        )

    with run_.timed("topics: neural head (PyTorch)"):
        train_vec, test_vec = dense[space]
        head = train_head(
            run_, train_vec[fit_idx], y_fit, train_vec[val_idx], y_val, len(names), epochs
        )
        probs = head["predict"](test_vec)
        score(
            f"neural_head_{space}",
            "two-layer neural head, trained with early stopping",
            embedders[space].label,
            probs.argmax(axis=1),
            head["seconds"],
            probs=probs,
            extra={"training": head["summary"]},
        )

    if llm is not None and llm_sample:
        with run_.timed("topics: local model, no training"):
            results_llm = zero_shot(run_, llm, test_text, test_y, names, llm_sample)
            run_.write("topics/llm_zero_shot.json", results_llm)
            confusions["llm_zero_shot"] = results_llm.pop("confusion")
            results["llm_zero_shot"] = results_llm

    best = max(
        (k for k in results if k != "llm_zero_shot"), key=lambda k: results[k]["macro_f1"]["value"]
    )
    run_.write("topics/classifiers.json", {"labels": names, "best": best, "results": results})
    run_.write("topics/confusion.json", {"labels": names, "matrices": confusions})
    return {
        "best": best,
        "results": {
            k: {"accuracy": v["accuracy"], "macro_f1": v["macro_f1"]} for k, v in results.items()
        },
    }


def clean(data: Topics):
    """Drop what cannot be learned from, and count what was dropped."""

    def norm(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    audit = {"raw": dict(data.raw_counts)}
    out = []
    for texts, labels in ((data.train_text, data.train_label), (data.test_text, data.test_label)):
        kept_t, kept_y, empty, seen, dupes = [], [], 0, set(), 0
        for text, label in zip(texts, labels, strict=True):
            n = norm(text)
            if len(n) < 20:  # nothing left once headers and quotes are gone
                empty += 1
                continue
            h = hashlib.sha256(n.lower().encode()).hexdigest()
            if h in seen:
                dupes += 1
                continue
            seen.add(h)
            kept_t.append(n)
            kept_y.append(label)
        out.append((kept_t, kept_y, empty, dupes, seen))
    (train_t, train_y, e1, d1, h1), (test_t, test_y, e2, d2, h2) = out
    exact_cross = h1 & h2
    if exact_cross:
        keep = [
            i
            for i, t in enumerate(test_t)
            if hashlib.sha256(t.lower().encode()).hexdigest() not in exact_cross
        ]
        test_t, test_y = [test_t[i] for i in keep], [test_y[i] for i in keep]
    audit.update(
        {
            "empty_after_cleaning": {"train": e1, "test": e2},
            "exact_duplicates_within": {"train": d1, "test": d2},
            "exact_duplicates_across_split": len(exact_cross),
            "after_cleaning": {"train": len(train_t), "test": len(test_t)},
        }
    )
    return train_t, train_y, test_t, test_y, audit


def profile_of(
    train_text, train_y, test_text, test_y, names, embedder: Embedder, audit: dict
) -> dict:
    from app.services.artifacts import tokens as token_budget

    est = np.array([token_budget.estimate(t[:MAX_CHARS]) for t in train_text])
    chars = np.array([len(t) for t in train_text])
    return {
        "audit": audit,
        "classes": names,
        "per_class": {
            n: {"train": int((train_y == c).sum()), "test": int((test_y == c).sum())}
            for c, n in enumerate(names)
        },
        "chars": metrics.percentiles(chars),
        "chars_histogram": metrics.histogram(np.minimum(chars, 6000), 0, 6000, 30),
        "truncated_to_chars": MAX_CHARS,
        "share_truncated": float((chars > MAX_CHARS).mean()),
        "token_estimate": metrics.percentiles(est),
        "payload_limit_tokens": embedder.limit,
        "share_over_payload_limit": float((est > embedder.limit).mean()),
        "embedding_model": embedder.label,
    }


def similarity(vectors: np.ndarray, labels: np.ndarray, names: list[str]) -> dict:
    """Same-topic versus different-topic similarity, and the Galaxy's centroid rule."""
    rng = np.random.default_rng(SEED)
    n = len(labels)
    a, b = rng.integers(0, n, 40000), rng.integers(0, n, 40000)
    distinct = a != b
    a, b = a[distinct], b[distinct]
    cos = (vectors[a] * vectors[b]).sum(axis=1)
    same = labels[a] == labels[b]
    auc, curve = metrics.roc_points(cos, same.astype(int))
    lo, hi = float(cos.min()), float(cos.max())

    centroids = np.stack([vectors[labels == c].mean(axis=0) for c in range(len(names))])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True).clip(min=1e-12)
    matrix = centroids @ centroids.T
    upper = matrix[np.triu_indices(len(names), 1)]
    typical, spread = float(upper.mean()), float(upper.std())
    # backend/app/services/similarity.py: an edge where a pair is more than
    # one standard deviation above the library's typical pair.
    threshold = typical + 1.0 * spread
    edges = sorted(
        (
            {"a": names[i], "b": names[j], "similarity": float(matrix[i, j])}
            for i in range(len(names))
            for j in range(i + 1, len(names))
            if matrix[i, j] > threshold
        ),
        key=lambda e: -e["similarity"],
    )
    from sklearn.metrics import silhouette_score

    sample = rng.choice(n, size=min(3000, n), replace=False)
    return {
        "pairs": int(len(cos)),
        "same_topic": metrics.histogram(cos[same], lo, hi),
        "different_topic": metrics.histogram(cos[~same], lo, hi),
        "same_topic_mean": float(cos[same].mean()),
        "different_topic_mean": float(cos[~same].mean()),
        "roc_auc_same_vs_different": auc,
        "roc": curve,
        "silhouette_cosine": float(
            silhouette_score(vectors[sample], labels[sample], metric="cosine")
        ),
        "centroid_matrix": matrix.round(4).tolist(),
        "galaxy_rule": {
            "typical": typical,
            "spread": spread,
            "threshold": threshold,
            "edges": edges[:12],
        },
    }


def projection(dense_test: np.ndarray, sparse_test, labels: np.ndarray, names: list[str]) -> dict:
    """Two-dimensional pictures of both spaces, from the same documents."""
    from sklearn.decomposition import PCA, TruncatedSVD
    from sklearn.metrics import silhouette_score

    rng = np.random.default_rng(SEED)
    sample = np.sort(
        rng.choice(len(labels), size=min(PROJECTION_SAMPLE, len(labels)), replace=False)
    )
    out = {"labels": names, "sample_labels": labels[sample].tolist()}
    pca = PCA(n_components=min(50, dense_test.shape[1], len(labels) - 1), random_state=SEED).fit(
        dense_test
    )
    coords = pca.transform(dense_test[sample])[:, :2]
    out["pca_dense"] = {
        "explained_variance": pca.explained_variance_ratio_.round(5).tolist(),
        "points": coords.round(4).tolist(),
        "silhouette_2d": float(silhouette_score(coords, labels[sample])),
    }
    svd = TruncatedSVD(n_components=min(50, sparse_test.shape[1] - 1), random_state=SEED).fit(
        sparse_test
    )
    coords = svd.transform(sparse_test[sample])[:, :2]
    out["svd_tfidf"] = {
        "explained_variance": svd.explained_variance_ratio_.round(5).tolist(),
        "points": coords.round(4).tolist(),
        "silhouette_2d": float(silhouette_score(coords, labels[sample])),
    }
    return out


def fit_and_score(score, name, desc, features, kind, x_fit, y_fit, x_val, y_val, x_test):
    """Pick the hyper-parameter on the validation split, refit, score once on test."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.svm import LinearSVC

    grid = {
        "knn": [{"n_neighbors": k, "metric": "cosine", "weights": "distance"} for k in (5, 15, 30)],
        "logreg": [{"C": c, "max_iter": 2000} for c in (0.5, 2.0, 8.0)],
        "svm": [{"C": c} for c in (0.1, 0.5, 2.0)],
        "forest": [
            {"n_estimators": 400, "max_features": m, "n_jobs": -1, "random_state": SEED}
            for m in ("sqrt", 0.05)
        ],
    }[kind]
    make = {
        "knn": KNeighborsClassifier,
        "logreg": LogisticRegression,
        "svm": LinearSVC,
        "forest": RandomForestClassifier,
    }[kind]
    started = time.perf_counter()
    trials = []
    for params in grid:
        model = make(**params).fit(x_fit, y_fit)
        trials.append((float((model.predict(x_val) == y_val).mean()), params, model))
    accuracy, params, model = max(trials, key=lambda t: t[0])
    probs = model.predict_proba(x_test) if hasattr(model, "predict_proba") else None
    score(
        name,
        desc,
        features,
        model.predict(x_test),
        time.perf_counter() - started,
        probs=probs,
        extra={
            "chosen": {k: v for k, v in params.items() if k not in {"n_jobs", "random_state"}},
            "validation_accuracy": accuracy,
            "validation_trials": [
                {
                    "params": {k: v for k, v in p.items() if k not in {"n_jobs", "random_state"}},
                    "accuracy": a,
                }
                for a, p, _ in trials
            ],
        },
    )
    return model


def train_head(run_: Run, x_fit, y_fit, x_val, y_val, classes: int, epochs: int) -> dict:
    """A two-layer head on frozen embeddings, trained on the GPU when there is one."""
    import torch
    from torch import nn

    torch.manual_seed(SEED)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    model = nn.Sequential(
        nn.Linear(x_fit.shape[1], 512), nn.GELU(), nn.Dropout(0.3), nn.Linear(512, classes)
    ).to(device)
    optimiser = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-2)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=epochs)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)
    # Standardised with the training split's own statistics, kept with the checkpoint.
    mean, std = x_fit.mean(axis=0), x_fit.std(axis=0) + 1e-6
    xf, yf = torch.tensor((x_fit - mean) / std, device=device), torch.tensor(y_fit, device=device)
    xv, yv = torch.tensor((x_val - mean) / std, device=device), torch.tensor(y_val, device=device)
    curve, best, best_state, patience, waited = [], float("inf"), None, 8, 0
    started = time.perf_counter()
    for epoch in range(1, epochs + 1):
        tick = time.perf_counter()
        model.train()
        order = torch.randperm(len(xf), device=device)
        total, correct = 0.0, 0
        for start in range(0, len(order), 256):
            batch = order[start : start + 256]
            logits = model(xf[batch])
            loss = loss_fn(logits, yf[batch])
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            total += loss.item() * len(batch)
            correct += int((logits.argmax(1) == yf[batch]).sum())
        scheduler.step()
        model.eval()
        with torch.no_grad():
            logits = model(xv)
            val_loss = float(loss_fn(logits, yv))
            val_acc = float((logits.argmax(1) == yv).float().mean())
        seconds = time.perf_counter() - tick
        curve.append(
            {
                "epoch": epoch,
                "train_loss": total / len(xf),
                "train_accuracy": correct / len(xf),
                "val_loss": val_loss,
                "val_accuracy": val_acc,
                "lr": scheduler.get_last_lr()[0],
                "seconds": round(seconds, 3),
                "examples_per_second": round(len(xf) / seconds, 1),
            }
        )
        if val_loss < best - 1e-4:
            best, waited = val_loss, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            best_epoch = epoch
        else:
            waited += 1
            if waited >= patience:
                break
    elapsed = time.perf_counter() - started
    model.load_state_dict(best_state)
    checkpoint = run_.out / "topics" / "neural_head.pt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": best_state,
            "input_dim": x_fit.shape[1],
            "classes": classes,
            "mean": torch.tensor(mean),
            "std": torch.tensor(std),
        },
        checkpoint,
    )
    run_.write("topics/training_curve.json", curve)
    summary = {
        "device": torch.cuda.get_device_name(0) if device == "cuda" else "cpu",
        "epochs_run": len(curve),
        "best_epoch": best_epoch,
        "max_epochs": epochs,
        "early_stopping_patience": patience,
        "best_val_loss": best,
        "train_examples": len(xf),
        "val_examples": len(xv),
        "parameters": sum(p.numel() for p in model.parameters()),
        "optimiser": "AdamW lr 1e-3, weight decay 1e-2, cosine schedule, "
        "label smoothing 0.05, batch 256",
        "inputs": "standardised with the training split's mean and standard deviation",
        "seconds": round(elapsed, 2),
        "peak_gpu_memory_mb": round(torch.cuda.max_memory_allocated() / 2**20, 1)
        if device == "cuda"
        else None,
        "checkpoint": checkpoint.name,
        "checkpoint_sha256": sha256_of(checkpoint),
    }

    def predict(x: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            return (
                torch.softmax(model(torch.tensor((x - mean) / std, device=device)), dim=1)
                .cpu()
                .numpy()
            )

    return {"predict": predict, "summary": summary, "seconds": elapsed}


_READABLE = {
    "alt.atheism": "atheism",
    "comp.graphics": "computer graphics",
    "comp.os.ms-windows.misc": "Microsoft Windows",
    "comp.sys.ibm.pc.hardware": "IBM PC hardware",
    "comp.sys.mac.hardware": "Mac hardware",
    "comp.windows.x": "X Window System",
    "misc.forsale": "for sale",
    "rec.autos": "cars",
    "rec.motorcycles": "motorcycles",
    "rec.sport.baseball": "baseball",
    "rec.sport.hockey": "hockey",
    "sci.crypt": "cryptography",
    "sci.electronics": "electronics",
    "sci.med": "medicine",
    "sci.space": "space",
    "soc.religion.christian": "Christianity",
    "talk.politics.guns": "gun politics",
    "talk.politics.mideast": "Middle East politics",
    "talk.politics.misc": "politics (other)",
    "talk.religion.misc": "religion (other)",
}


def zero_shot(
    run_: Run, llm: LocalModel, texts: list[str], labels: np.ndarray, names: list[str], sample: int
) -> dict:
    """The local model picks a topic from the list, with no examples and no training."""
    from sklearn.metrics import confusion_matrix, f1_score

    readable = [_READABLE.get(n, n) for n in names]
    rng = np.random.default_rng(SEED)
    per_class = max(1, sample // len(names))
    chosen = np.concatenate(
        [
            rng.choice(
                np.flatnonzero(labels == c),
                size=min(per_class, int((labels == c).sum())),
                replace=False,
            )
            for c in range(len(names))
        ]
    )
    system = (
        "You label forum posts with exactly one topic from a fixed list. "
        "Reply with the topic only, copied exactly from the list."
    )
    preds, invalid, durations = [], 0, []
    lookup = {r.lower(): i for i, r in enumerate(readable)}
    for n, i in enumerate(chosen):
        prompt = (
            "Topics:\n"
            + "\n".join(f"- {r}" for r in readable)
            + f"\n\nPost:\n{texts[i][:1500]}\n\nTopic:"
        )
        generated = llm.generate(prompt, system=system)
        durations.append(generated.duration_ms)
        answer = generated.text.strip().strip(".").strip("-* ").lower()
        guess = lookup.get(answer)
        if guess is None:
            guess = next((idx for r, idx in lookup.items() if r in answer), None)
        if guess is None:
            invalid += 1
            guess = -1
        preds.append(guess)
        if n % 50 == 0:
            run_.log(f"   local model: {n}/{len(chosen)}")
    truth = labels[chosen]
    # An unusable reply is its own column, "none of the list": wrong, and visibly so.
    pred = np.where(np.array(preds) < 0, len(names), np.array(preds))
    topics = list(range(len(names)))
    return {
        "model": f"{llm.model} (no training, no examples)",
        "features": "the post's text",
        "sample": int(len(chosen)),
        "unusable_replies": invalid,
        **metrics.bootstrap_classification(truth, pred, labels=topics),
        "weighted_f1": float(
            f1_score(truth, pred, labels=topics, average="weighted", zero_division=0)
        ),
        "latency_ms": metrics.percentiles(durations),
        "confusion": confusion_matrix(truth, pred, labels=[*topics, len(names)]).tolist(),
    }
