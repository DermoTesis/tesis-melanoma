import csv
import json

import yaml

from melanoma.runs import consolidate_results, start_run

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
