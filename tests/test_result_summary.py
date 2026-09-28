from __future__ import annotations

import json

from crosfed.experiments.reporting import aggregate_runs, load_run, write_outputs


def test_result_summary_computes_seed_statistics(tmp_path) -> None:
    runs = []
    for seed, accuracy in [(1, 0.8), (2, 1.0)]:
        path = tmp_path / f"run-{seed}.json"
        path.write_text(
            json.dumps(
                {
                    "run_id": f"run-{seed}",
                    "status": "passed",
                    "wall_seconds": 2.0,
                    "config": {
                        "seed": seed,
                        "dataset": "mnist",
                        "mode": "plain",
                        "model": "tiny",
                        "clients": 2,
                    },
                    "rounds": [{"accuracy": accuracy, "loss": 0.5, "protocol": None}],
                }
            ),
            encoding="utf-8",
        )
        runs.append(load_run(path))
    rows = aggregate_runs([run for run in runs if run is not None])
    assert len(rows) == 1
    assert rows[0]["seeds"] == 2
    assert rows[0]["final_accuracy_mean"] == 0.9
    assert rows[0]["final_accuracy_std"] > 0
    prefix = tmp_path / "summary"
    write_outputs(rows, prefix)
    assert prefix.with_suffix(".json").exists()
    assert prefix.with_suffix(".csv").exists()
