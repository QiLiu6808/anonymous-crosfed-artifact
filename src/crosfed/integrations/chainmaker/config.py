from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a deployable CrosFed ChainMaker config")
    parser.add_argument("--template", default="chainmaker/config/example.yaml")
    parser.add_argument("--cmc", required=True)
    parser.add_argument("--institution-sdk", required=True)
    parser.add_argument("--aggregator-sdk", required=True)
    parser.add_argument("--relay-sdk", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--check-paths", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.template).read_text(encoding="utf-8"))
    chain_ids = [
        config["institution_chain"]["chain_id"],
        config["aggregator_chain"]["chain_id"],
        config["relay"]["chain_id"],
    ]
    paths = [args.cmc, args.institution_sdk, args.aggregator_sdk, args.relay_sdk]
    if args.check_paths:
        missing = [value for value in paths if not Path(value).exists()]
        if missing:
            raise FileNotFoundError("missing ChainMaker paths: " + ", ".join(missing))
    config["cmc"]["executable"] = args.cmc
    config["cmc"]["sdk_conf_by_chain"] = dict(
        zip(chain_ids, [args.institution_sdk, args.aggregator_sdk, args.relay_sdk])
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    config["sdk_bridge"]["command"] = [
        "python", "-m", "crosfed.cli.chainmaker_bridge", "--config", str(output)
    ]
    output.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    main()
