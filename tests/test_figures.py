import numpy as np

from melanoma.figures import by_diagnosis, confusion_table, plot_matrices


def test_confusion_table_rows_are_real_class_and_columns_prediction():
    y = [1, 1, 1, 0, 0, 0, 0]
    p = [0.9, 0.6, 0.2, 0.7, 0.4, 0.1, 0.0]
    np.testing.assert_array_equal(confusion_table(y, p, 0.5), [[2, 1], [1, 3]])


def test_by_diagnosis_counts_predicted_melanoma_in_display_order():
    dx = ["nv", "mel", "mel", "bcc", "nv", "nv"]
    p = [0.6, 0.9, 0.1, 0.8, 0.2, 0.3]
    table = by_diagnosis(dx, p, 0.5)
    assert list(table.index) == ["mel", "nv", "bcc"]
    assert table.loc["nv", "images"] == 3 and table.loc["nv", "predicted_melanoma"] == 1
    assert table.loc["mel", "fraction"] == 0.5


def test_plot_matrices_writes_png(tmp_path):
    import pytest
    pytest.importorskip("matplotlib")
    path = plot_matrices([("Umbral 0.5", np.array([[2, 1], [1, 3]]))], ["Melanoma", "No melanoma"],
                         tmp_path / "m.png", title="Prueba")
    assert path.read_bytes()[:4] == b"\x89PNG"
