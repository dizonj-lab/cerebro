"""The measures against values worked out by hand."""

from __future__ import annotations

import math

import numpy as np
import pytest
from cerebro_eval import metrics


def test_ndcg_is_one_for_the_ideal_order_and_lower_otherwise():
    rel = {"a": 2, "b": 1}
    assert metrics.ndcg_at(["a", "b", "c"], rel) == pytest.approx(1.0)
    swapped = (1 / math.log2(2) + 3 / math.log2(3)) / (3 / math.log2(2) + 1 / math.log2(3))
    assert metrics.ndcg_at(["b", "a"], rel) == pytest.approx(swapped)
    assert metrics.ndcg_at(["x", "y"], rel) == 0.0


def test_recall_and_mrr():
    rel = {"a": 1, "b": 1}
    assert metrics.recall_at(["x", "a", "y"], rel, 10) == 0.5
    assert metrics.mrr_at(["x", "a", "b"], rel) == 0.5
    assert metrics.mrr_at(["x"] * 10 + ["a"], rel, 10) == 0.0


def test_rrf_matches_the_product_rule():
    # 1/(60+1) + 1/(60+2) for "b" beats 1/(60+1) for "a" alone.
    assert metrics.rrf(["a", "b"], ["b", "c"])[0] == "b"
    assert metrics.rrf(["a"], []) == ["a"]


def test_a_document_ranks_where_its_best_fragment_ranks():
    owner = {"d1#0": "d1", "d1#1": "d1", "d2#0": "d2"}
    assert metrics.documents_from_fragments(
        [("d1#1", 0.9), ("d2#0", 0.8), ("d1#0", 0.7)], owner
    ) == ["d1", "d2"]


def test_bm25_prefers_the_document_with_the_rare_term():
    index = metrics.BM25({"a": "cat sat on the mat", "b": "dog sat on the log", "c": "the the the"})
    assert index.search("cat")[0][0] == "a"
    assert index.search("unseen") == []


def test_squad_normalisation_and_containment():
    assert metrics.normalise_answer("The  Eiffel Tower!") == "eiffel tower"
    assert metrics.contains_answer("It was built by Gustave Eiffel [1].", "Gustave Eiffel")
    assert not metrics.contains_answer("It was built by Eiffel.", "Gustave Eiffel")
    assert metrics.answer_f1("Gustave Eiffel", "Eiffel") == pytest.approx(2 / 3)
    assert metrics.answer_recall("Eiffel built it", "Gustave Eiffel") == 0.5


def test_calibration_of_a_perfectly_calibrated_model_is_zero():
    probs = np.array([[0.75, 0.25]] * 4)
    labels = np.array([0, 0, 0, 1])
    ece, bins = metrics.expected_calibration_error(probs, labels)
    assert ece == pytest.approx(0.0)
    assert bins[0]["count"] == 4


def test_bootstrap_interval_contains_the_mean():
    result = metrics.bootstrap([0, 1] * 50)
    assert result["value"] == 0.5
    assert result["ci95"][0] < 0.5 < result["ci95"][1]


def test_paired_bootstrap_detects_a_consistent_difference():
    result = metrics.paired_bootstrap([1.0] * 30, [0.0] * 30)
    assert result["mean_difference"] == 1.0
    assert result["p_two_sided"] == 0.0


def test_macro_f1_ignores_a_none_of_the_list_column():
    out = metrics.bootstrap_classification([0, 1, 1], [0, 1, 2], labels=[0, 1])
    # Class 1: precision 1, recall 0.5 → F1 2/3; class 0: F1 1.
    assert out["macro_f1"]["value"] == pytest.approx((1 + 2 / 3) / 2)
