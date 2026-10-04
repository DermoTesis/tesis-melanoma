"""Conversión a .tflite e inferencia como en el backend (EXP-05), con un modelo chico sin pesos."""

import os

import numpy as np
import pytest

tf = pytest.importorskip("tensorflow")
keras = pytest.importorskip("keras")
pytest.importorskip("ai_edge_litert")
pytest.importorskip("PIL")

from melanoma.data.pipeline import load_image  # noqa: E402
from melanoma.export_tflite import benchmark, cold_start, convert  # noqa: E402
from melanoma.models import build_single_view, build_two_view  # noqa: E402
from melanoma.serving import TFLiteClassifier, preprocess  # noqa: E402

SIZE = 64


@pytest.fixture(scope="module")
def model():
    keras.mixed_precision.set_global_policy("float32")
    return build_single_view({"backbone": "mobilenet_v3_large", "weights": None, "dropout": 0.2},
                             SIZE)


@pytest.fixture(scope="module")
def jpegs():
    rng = np.random.default_rng(0)
    return [tf.io.encode_jpeg(rng.integers(0, 255, (45, 60, 3), dtype=np.uint8)).numpy()
            for _ in range(4)]


def test_pillow_preprocessing_matches_training(jpegs, tmp_path):
    path = tmp_path / "a.jpg"
    path.write_bytes(jpegs[0])
    ours = preprocess(jpegs[0], SIZE)
    training = load_image(tf.constant(str(path)), SIZE).numpy()
    assert ours.shape == training.shape == (SIZE, SIZE, 3) and ours.dtype == np.uint8
    assert np.abs(ours.astype(int) - training.astype(int)).mean() < 3


@pytest.mark.parametrize("fmt", ["float32", "float16", "dynamic_range"])
def test_converted_model_predicts_like_keras(model, jpegs, fmt):
    images = np.stack([preprocess(j, SIZE) for j in jpegs])
    expected = model.predict(images.astype("float32"), verbose=0).ravel()
    clf = TFLiteClassifier(convert(model, fmt), num_threads=1)
    tolerance = 1e-5 if fmt == "float32" else 0.1
    np.testing.assert_allclose(clf.predict(images), expected, atol=tolerance)


def test_int8_needs_representative_images(model):
    with pytest.raises(ValueError):
        convert(model, "int8")


def test_benchmark_and_cold_start_report_latencies(model, jpegs, tmp_path):
    path = tmp_path / "m.tflite"
    path.write_bytes(convert(model, "float32"))
    cpus = os.sched_getaffinity(0)   # benchmark limita los núcleos del proceso que lo llama
    try:
        out = benchmark(path, jpegs, SIZE, threads=1, warmup=1, runs=4, concurrent=2)
    finally:
        os.sched_setaffinity(0, cpus)
    for key in ("photo_ms", "case_ms", "case_concurrent_ms", "case_full_concurrent_ms"):
        assert 0 < out[key]["p50"] <= out[key]["p95"]
    assert out["xnnpack"] is True
    cold = cold_start(path, threads=1, image_size=SIZE, runs=1)
    assert cold["total_s"]["p95"] > cold["load_and_first_inference_s"] > 0


def test_two_view_model_converts_and_classifies_a_case_in_one_call(model, jpegs, tmp_path):
    two = build_two_view(model, {"hidden": 8})
    a, b = (np.stack([preprocess(j, SIZE) for j in jpegs[k::2]]) for k in (0, 1))
    expected = two.predict({"view_a": a.astype("float32"), "view_b": b.astype("float32")},
                           verbose=0).ravel()
    clf = TFLiteClassifier(convert(two, "float32"), num_threads=1)
    assert clf.n_inputs == 2
    np.testing.assert_allclose(clf.predict(list(zip(a, b))), expected, atol=1e-5)
    assert clf.predict_case(a[0], b[0]) == pytest.approx([expected[0]], abs=1e-5)
    int8 = convert(two, "int8", representative=list(zip(a, b)))
    assert TFLiteClassifier(int8, num_threads=1).predict_case(a[0], b[0])[0] >= 0
    single = TFLiteClassifier(convert(model, "float32"), num_threads=1)
    assert len(single.predict_case(a[0], b[0])) == 2
    path = tmp_path / "two.tflite"
    path.write_bytes(convert(two, "float32"))
    cpus = os.sched_getaffinity(0)
    try:
        out = benchmark(path, jpegs, SIZE, threads=1, warmup=1, runs=4, concurrent=2)
    finally:
        os.sched_setaffinity(0, cpus)
    assert out["case_ms"]["p50"] > 0
    assert cold_start(path, threads=1, image_size=SIZE, runs=1)["total_s"]["p95"] > 0
