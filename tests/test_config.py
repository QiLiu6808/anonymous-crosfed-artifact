from __future__ import annotations

import pytest

from crosfed.config import validate_experiment_config


def base_config() -> dict:
    return {
        "run_id": "test", "seed": 1, "mode": "plain", "dataset": "mnist",
        "data_dir": "data", "model": "paper_candidate", "clients": 2,
        "rounds": 1, "local_epochs": 1, "batch_size": 8, "learning_rate": 0.1,
    }


def test_plain_config_is_valid() -> None:
    validate_experiment_config(base_config())


def test_crypto_committee_is_validated() -> None:
    config = {
        **base_config(), "mode": "crypto", "aggregators": 3, "threshold": 2,
        "committee": [1, 4], "codec": {"scale": 100, "clip": 8},
    }
    with pytest.raises(ValueError, match="out of range"):
        validate_experiment_config(config)
