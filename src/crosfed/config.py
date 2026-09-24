from __future__ import annotations

from typing import Any, Mapping


def validate_experiment_config(config: Mapping[str, Any]) -> None:
    required = {
        "run_id", "seed", "mode", "dataset", "data_dir", "model", "clients",
        "rounds", "local_epochs", "batch_size", "learning_rate",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"missing experiment config fields: {', '.join(missing)}")
    if config["mode"] not in {"plain", "crypto", "hybridalpha", "privldfl"}:
        raise ValueError("unsupported experiment mode")
    if config["dataset"] not in {"mnist", "cifar10"}:
        raise ValueError("unsupported dataset")
    for field in ("clients", "rounds", "local_epochs", "batch_size"):
        if int(config[field]) <= 0:
            raise ValueError(f"{field} must be positive")
    if float(config["learning_rate"]) <= 0:
        raise ValueError("learning_rate must be positive")

    if config["mode"] == "crypto":
        for field in ("aggregators", "threshold", "codec"):
            if field not in config:
                raise ValueError(f"crypto mode requires {field}")
        aggregators = int(config["aggregators"])
        threshold = int(config["threshold"])
        if not 1 <= threshold <= aggregators:
            raise ValueError("threshold must be in [1, aggregators]")
        committee = tuple(int(value) for value in config.get("committee", range(1, threshold + 1)))
        if len(set(committee)) != len(committee) or len(committee) < threshold:
            raise ValueError("committee must contain at least threshold unique identities")
        if any(value < 1 or value > aggregators for value in committee):
            raise ValueError("committee identity out of range")
    if config.get("ledger_backend", "memory") == "chainmaker" and "chainmaker_config" not in config:
        raise ValueError("ChainMaker backend requires chainmaker_config")

    codec = config.get("codec")
    if codec is not None:
        if int(codec.get("scale", 0)) <= 0 or float(codec.get("clip", 0)) <= 0:
            raise ValueError("codec scale and clip must be positive")
