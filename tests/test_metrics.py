import math

import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from melanoma.metrics import (at_threshold, bootstrap_indices, cv_summary, evaluate, point_metrics,
                              threshold_for_recall)


def test_confusion_metrics_by_hand():
    y = np.array([1, 1, 1, 0, 0, 0, 0, 0])
    p = np.array([0.9, 0.6, 0.2, 0.7, 0.4, 0.3, 0.1, 0.0])
    m = at_threshold(y, p, 0.5)
    assert (m["tp"], m["fp"], m["tn"], m["fn"]) == (2, 1, 4, 1)
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["precision"] == pytest.approx(2 / 3)
    assert m["specificity"] == pytest.approx(4 / 5)
    assert m["accuracy"] == pytest.approx(6 / 8)
    assert m["f1"] == pytest.approx(2 / 3)


def test_threshold_is_inclusive_and_no_positive_predictions_give_zero():
    m = at_threshold(np.array([1, 0]), np.array([0.5, 0.2]), 0.5)
    assert m["tp"] == 1
    m = at_threshold(np.array([1, 0]), np.array([0.1, 0.2]), 0.9)
    assert m["precision"] == 0.0 and m["f1"] == 0.0


def test_threshold_for_recall_is_the_highest_that_reaches_target():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 500)
    p = rng.random(500)
    t = threshold_for_recall(y, p, 0.9)
    assert at_threshold(y, p, t)["recall"] >= 0.9
    above = np.min(p[p > t])   # el siguiente umbral posible ya no alcanza el objetivo
    assert at_threshold(y, p, above)["recall"] < 0.9


def test_point_metrics_match_sklearn_and_use_suffixes():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 300)
    p = np.clip(y * 0.3 + rng.random(300) * 0.7, 0, 1)
    m = point_metrics(y, p, 0.9)
    assert m["auc_roc"] == pytest.approx(roc_auc_score(y, p))
    assert {"recall_t50", "specificity_s90", "threshold_s90", "tp_s90"} <= set(m)
    assert m["recall_s90"] >= 0.9


def test_point_metrics_without_both_classes_give_nan_auc():
    m = point_metrics(np.zeros(5, dtype=int), np.linspace(0, 1, 5))
    assert math.isnan(m["auc_roc"]) and math.isnan(m["threshold_s90"])


def test_bootstrap_keeps_whole_lesions_together():
    groups = np.array(["a", "a", "a", "b", "c", "c", "d"])
    size = {"a": 3, "b": 1, "c": 2, "d": 1}
    for idx in bootstrap_indices(groups, 200, seed=0):
        picked, counts = np.unique(groups[idx], return_counts=True)
        for g, n in zip(picked, counts):
            assert n % size[g] == 0
        # Se eligen tantas lesiones como hay, con reemplazo.
        assert sum(n // size[g] for g, n in zip(picked, counts)) == 4


def test_bootstrap_by_lesion_is_wider_than_by_image():
    # 40 lesiones con 10 imágenes casi idénticas cada una: la incertidumbre real es la de 40
    # casos, no la de 400 imágenes.
    rng = np.random.default_rng(2)
    lesion_y = rng.integers(0, 2, 40)
    lesion_p = np.clip(lesion_y * 0.2 + rng.random(40) * 0.8, 0, 1)
    y = np.repeat(lesion_y, 10)
    p = np.repeat(lesion_p, 10) + rng.normal(0, 1e-3, 400)
    by_lesion = evaluate(y, p, np.repeat(np.arange(40), 10), n_resamples=300, seed=0)
    by_image = evaluate(y, p, np.arange(400), n_resamples=300, seed=0)
    width = lambda m: m["auc_roc_ci_high"] - m["auc_roc_ci_low"]
    assert width(by_lesion) > 2 * width(by_image)
    assert by_lesion["n_lesions"] == 40 and by_lesion["n_images"] == 400
    assert by_lesion["auc_roc_ci_low"] <= by_lesion["auc_roc"] <= by_lesion["auc_roc_ci_high"]
    assert "tp_t50_ci_low" not in by_lesion


def test_cv_summary_mean_and_sample_std():
    s = cv_summary([{"fold": 0, "auc_roc": 0.8}, {"fold": 1, "auc_roc": 0.9}])
    assert s["auc_roc"]["mean"] == pytest.approx(0.85)
    assert s["auc_roc"]["std"] == pytest.approx(np.std([0.8, 0.9], ddof=1))
    assert "fold" not in s
