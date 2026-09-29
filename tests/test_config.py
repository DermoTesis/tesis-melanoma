from pathlib import Path

import pytest

from melanoma.config import load_config, parse_override

CONFIGS = Path(__file__).resolve().parents[1] / "configs"


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_extends_merges_nested_sections(tmp_path):
    write(tmp_path / "base.yaml", "a: 1\ntraining: {batch_size: 32, lr: 0.1}\n")
    child = write(tmp_path / "exp.yaml", "extends: base.yaml\ntraining: {batch_size: 16}\n")
    cfg = load_config(child)
    assert cfg == {"a": 1, "training": {"batch_size": 16, "lr": 0.1}}


def test_overrides_are_parsed_as_yaml(tmp_path):
    cfg_path = write(tmp_path / "c.yaml", "training: {lr: 0.1}\n")
    cfg = load_config(cfg_path, ["training.lr=1e-5", "model.heads=[dense, random_forest]"])
    assert cfg["training"]["lr"] == pytest.approx(1e-5)
    assert cfg["model"]["heads"] == ["dense", "random_forest"]


def test_scientific_notation_without_dot_is_float():
    assert parse_override("x=1e-3") == ("x", 0.001)


def test_circular_extends_is_rejected(tmp_path):
    write(tmp_path / "a.yaml", "extends: b.yaml\n")
    write(tmp_path / "b.yaml", "extends: a.yaml\n")
    with pytest.raises(ValueError, match="circular"):
        load_config(tmp_path / "a.yaml")


@pytest.mark.parametrize("path", sorted(CONFIGS.glob("exp*.yaml")), ids=lambda p: p.stem)
def test_experiment_configs_load(path):
    cfg = load_config(path)
    assert cfg["experiment"] == path.stem.split("_")[0]
    assert cfg["metrics"]["target_recall"] == 0.90
    assert cfg["split"]["group_column"] == "lesion_id"
