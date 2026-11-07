import csv
import json
import shutil
import subprocess

import pytest
import yaml

from melanoma.runs import _git_info, _read_head, consolidate_results, start_run

CFG = {"paths": {"results": "resultados", "outputs": "outputs"}, "seed": 42}


def test_run_saves_config_environment_and_metrics(tmp_path):
    run = start_run(CFG, "exp02", "V3 Large + densa", root=tmp_path)
    assert run.run_id.endswith("_v3-large-densa")
    assert run.artifacts_dir == tmp_path / "outputs" / "exp02" / run.run_id
    assert yaml.safe_load((run.results_dir / "config.yaml").read_text()) == CFG
    assert "packages" in json.loads((run.results_dir / "entorno.json").read_text())

    run.save_metrics([{"fold": 0, "auc_roc": 0.91}], details={"roc": [[0, 0], [1, 1]]})
    saved = json.loads((run.results_dir / "metricas.json").read_text())
    assert saved["rows"] == [{"fold": 0, "auc_roc": 0.91}]
    assert saved["details"]["roc"] == [[0, 0], [1, 1]]


def test_consolidation_unions_columns_across_runs(tmp_path):
    for exp, run_id, rows in [("exp02", "r1", [{"fold": 0, "auc_roc": 0.9}]),
                              ("exp03", "r2", [{"fold": 0, "auc_roc": 0.8, "strategy": "focal_loss"}])]:
        d = tmp_path / exp / run_id
        d.mkdir(parents=True)
        (d / "metricas.json").write_text(json.dumps({"experiment": exp, "run_id": run_id, "rows": rows}))
    with consolidate_results(tmp_path).open() as f:
        table = list(csv.DictReader(f))
    assert [r["experiment"] for r in table] == ["exp02", "exp03"]
    assert table[0]["strategy"] == "" and table[1]["strategy"] == "focal_loss"


def test_commit_is_read_from_git_dir_without_git(tmp_path):
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "packed-refs").write_text("# pack-refs\nabc123 refs/heads/main\n")
    assert _read_head(git) == "abc123"
    (git / "refs" / "heads" / "main").write_text("def456\n")
    assert _read_head(git) == "def456"
    assert _read_head(tmp_path / "no-existe") is None


@pytest.mark.skipif(shutil.which("git") is None, reason="sin git")
def test_changed_results_do_not_make_the_tree_dirty(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "resultados").mkdir()
    (tmp_path / "resultados" / "resultados.csv").write_text("a\n")
    (tmp_path / "codigo.py").write_text("x = 1\n")
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "inicial")
    (tmp_path / "resultados" / "resultados.csv").write_text("a\nb\n")
    assert _git_info(tmp_path, ("resultados",))["dirty"] is False
    assert _git_info(tmp_path)["dirty"] is True
    (tmp_path / "codigo.py").write_text("x = 2\n")
    assert _git_info(tmp_path, ("resultados",))["dirty"] is True


def test_reopened_run_must_have_the_same_config(tmp_path):
    from melanoma.runs import reopen_run

    cfg = {**CFG, "resume": None}
    run = start_run(cfg, "exp08", "pérdidas", root=tmp_path)
    again = reopen_run({**cfg, "resume": f"exp08/{run.run_id}"}, f"exp08/{run.run_id}", root=tmp_path)
    assert again == run
    assert list(run.results_dir.glob("entorno_reanudacion_*.json"))
    with pytest.raises(SystemExit, match="seed"):
        reopen_run({**cfg, "seed": 7}, f"exp08/{run.run_id}", root=tmp_path)
    with pytest.raises(SystemExit, match="No existe"):
        reopen_run(cfg, "exp08/no-existe", root=tmp_path)
