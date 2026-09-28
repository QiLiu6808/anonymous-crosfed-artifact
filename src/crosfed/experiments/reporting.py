from __future__ import annotations

import argparse
import csv
import glob
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


GROUP_FIELDS = (
    "dataset",
    "mode",
    "model",
    "candidate",
    "clients",
    "aggregators",
    "threshold",
)
METRIC_FIELDS = (
    "final_accuracy",
    "final_loss",
    "wall_seconds",
    "client_compute_seconds_mean",
    "aggregator_compute_seconds_mean",
    "client_upload_crypto_bytes_mean",
    "client_download_crypto_bytes_per_institution",
)


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _std(values: list[float]) -> float | None:
    if not values:
        return None
    return statistics.stdev(values) if len(values) > 1 else 0.0


def load_run(path: Path) -> dict[str, Any] | None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("status") != "passed"
        or not payload.get("rounds")
        or not isinstance(payload.get("config"), dict)
    ):
        return None
    config = payload["config"]
    final_round = payload["rounds"][-1]
    protocol = final_round.get("protocol") or {}
    derived = final_round.get("evidence", {}).get("paper_derived", {})
    upload_values = derived.get("client_upload_crypto_bytes_by_id")
    if upload_values is None:
        upload_values = protocol.get("client_crypto_bytes_by_id", [])
    return {
        "path": str(path),
        "run_id": payload.get("run_id"),
        "seed": config.get("seed"),
        "dataset": config.get("dataset"),
        "mode": config.get("mode"),
        "model": config.get("model"),
        "candidate": config.get("candidate"),
        "clients": config.get("clients"),
        "aggregators": config.get("aggregators"),
        "threshold": config.get("threshold"),
        "final_accuracy": final_round.get("accuracy"),
        "final_loss": final_round.get("loss"),
        "wall_seconds": payload.get("wall_seconds"),
        "client_compute_seconds_mean": derived.get("client_compute_seconds_mean"),
        "aggregator_compute_seconds_mean": derived.get(
            "aggregator_compute_seconds_mean"
        ),
        "client_upload_crypto_bytes_mean": _mean(
            [float(value) for value in upload_values]
        ),
        "client_download_crypto_bytes_per_institution": derived.get(
            "client_download_crypto_bytes_per_institution",
            sum(protocol.get("aggregator_crypto_bytes_by_id", [])) or None,
        ),
        "exact_oracle_match": protocol.get("exact_oracle_match"),
    }


def aggregate_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[tuple(run.get(field) for field in GROUP_FIELDS)].append(run)
    rows = []
    for key, samples in sorted(grouped.items(), key=lambda item: str(item[0])):
        row = dict(zip(GROUP_FIELDS, key))
        row["seeds"] = len(samples)
        row["run_ids"] = [sample["run_id"] for sample in samples]
        oracle_values = [
            sample["exact_oracle_match"]
            for sample in samples
            if sample["exact_oracle_match"] is not None
        ]
        row["all_exact_oracle_match"] = (
            all(oracle_values) if oracle_values else None
        )
        for field in METRIC_FIELDS:
            values = [float(sample[field]) for sample in samples if sample.get(field) is not None]
            row[f"{field}_mean"] = _mean(values)
            row[f"{field}_std"] = _std(values)
        rows.append(row)
    return rows


def write_outputs(rows: list[dict[str, Any]], output_prefix: Path) -> None:
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_prefix.with_suffix(".json")
    csv_path = output_prefix.with_suffix(".csv")
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    fieldnames = list(GROUP_FIELDS) + ["seeds", "run_ids", "all_exact_oracle_match"]
    for field in METRIC_FIELDS:
        fieldnames.extend((f"{field}_mean", f"{field}_std"))
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            serialized = dict(row)
            serialized["run_ids"] = ";".join(row["run_ids"])
            writer.writerow(serialized)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", action="append", default=["runs/**/result.json"])
    parser.add_argument("--output-prefix", default="runs/summary/paper_metrics")
    args = parser.parse_args()
    paths = sorted(
        {
            Path(match)
            for pattern in args.results
            for match in glob.glob(pattern, recursive=True)
        }
    )
    runs = [run for path in paths if (run := load_run(path)) is not None]
    rows = aggregate_runs(runs)
    write_outputs(rows, Path(args.output_prefix))
    print(json.dumps({"runs": len(runs), "groups": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
