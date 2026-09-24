from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import sys
from pathlib import Path

import yaml


def combinations(parameters: dict[str, list]) -> list[dict]:
    keys = list(parameters)
    return [dict(zip(keys, values)) for values in itertools.product(*(parameters[key] for key in keys))]


def normalize_threshold(config: dict) -> None:
    aggregators = int(config.get("aggregators", 1))
    if aggregators == 1:
        config["threshold"] = 1
        config["committee"] = [1]
    else:
        config["threshold"] = min(int(config.get("threshold", 2)), aggregators)
        config["committee"] = list(range(1, config["threshold"] + 1))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep", required=True)
    parser.add_argument("--output-root", default="runs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sweep = yaml.safe_load(Path(args.sweep).read_text(encoding="utf-8"))
    base = yaml.safe_load(Path(sweep["base_config"]).read_text(encoding="utf-8"))
    generated_root = Path("configs/generated") / sweep["sweep_name"]
    generated_root.mkdir(parents=True, exist_ok=True)

    commands = []
    for index, overrides in enumerate(combinations(sweep["parameters"]), start=1):
        config = {**base, **sweep.get("fixed", {}), **overrides}
        normalize_threshold(config)
        suffix = "_".join(f"{key}-{value}" for key, value in overrides.items())
        run_id = f"{sweep['sweep_name']}_{suffix}"
        config["run_id"] = run_id
        config_path = generated_root / f"{index:03d}_{suffix}.yaml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        output = Path(args.output_root) / run_id / "result.json"
        command = [
            sys.executable,
            "scripts/run_federated.py",
            "--config",
            str(config_path),
            "--output",
            str(output),
        ]
        commands.append(command)
        print(json.dumps(command))
        if not args.dry_run:
            subprocess.run(command, check=True)

    manifest = generated_root / "commands.json"
    manifest.write_text(json.dumps(commands, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

