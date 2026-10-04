import numpy as np
import pytest

from melanoma import calibration
from melanoma.metrics import at_threshold, evaluate_at, threshold_for_recall


def data(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < 0.2).astype(int)
    # Puntajes mal calibrados: demasiado bajos para los positivos.
    p = 1 / (1 + np.exp(-(1.5 * y - 2 + rng.normal(0, 1, n))))
    return y, p ** 2, rng.integers(0, 5, n)


def test_calibration_reduces_ece_and_keeps_the_order():
    y, p, folds = data()
    out = calibration.choose(y, p, folds, ["platt", "isotonic"])
    assert out["chosen"] in ("platt", "isotonic")
    assert out["scores"][out["chosen"]]["ece"] < out["scores"]["none"]["ece"]
    platt = calibration.fit("platt", y, p)
    calibrated = calibration.apply(platt, p)
    assert np.all(np.diff(calibrated[np.argsort(p)]) >= -1e-12)   # monótona
    assert abs(calibrated.mean() - y.mean()) < 0.02
    with pytest.raises(ValueError):
        calibration.fit("beta", y, p)


def test_threshold_with_margin_is_lower_and_keeps_recall_on_new_data():
    y, p, _ = data(seed=1)
    groups = np.arange(len(y))
    out = calibration.threshold_with_margin(y, p, groups, 0.9, 0.95, 300, seed=0)
    assert out["threshold"] < out["threshold_no_margin"]
    assert out["threshold_no_margin"] == threshold_for_recall(y, p, 0.9)
    # En datos nuevos de la misma distribución, el umbral con margen casi siempre llega al 90%.
    hits = [at_threshold(*data(seed=s)[:2], out["threshold"])["recall"] >= 0.9 for s in range(2, 22)]
    assert np.mean(hits) >= 0.8


def test_evaluate_at_keeps_the_threshold_fixed_and_reports_npv():
    y = np.array([1, 1, 0, 0, 0, 1])
    p = np.array([0.9, 0.4, 0.3, 0.6, 0.1, 0.8])
    out = evaluate_at(y, p, np.arange(6), 0.5, n_resamples=50, seed=0)
    assert (out["tp"], out["fn"], out["fp"], out["tn"]) == (2, 1, 1, 2)
    assert out["npv"] == pytest.approx(2 / 3) and out["threshold"] == 0.5
    assert out["recall_ci_low"] <= out["recall"] <= out["recall_ci_high"]
