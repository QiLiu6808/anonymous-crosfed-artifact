from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import yaml

from crosfed.crypto import TMCFEError, ThresholdMCFE


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default="runs/R001_R002_crypto_sanity/result.json")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    scheme = ThresholdMCFE(config["group"])
    start = time.perf_counter()
    scheme.setup(config["clients"], config["dimension"])
    keys = scheme.generate_functional_keys(
        config["weights"], range(1, config["aggregators"] + 1),
        config["threshold"], config["round_id"]
    )
    ciphertexts = [
        scheme.encrypt(vector, scheme.encryption_key(index + 1), config["round_id"])
        for index, vector in enumerate(config["vectors"])
    ]
    shares = [
        scheme.share_decrypt(
            ciphertexts, config["weights"], keys[identity], config["committee"], config["round_id"]
        )
        for identity in config["committee"]
    ]
    recovered = scheme.combine(shares, config["round_id"], config["dlog_bound"])
    expected = [
        sum(config["vectors"][i][z] * config["weights"][i][z] for i in range(config["clients"]))
        for z in range(config["dimension"])
    ]

    negative_checks = {}
    cases = {
        "t_minus_one": lambda: scheme.combine(shares[:-1], config["round_id"], config["dlog_bound"]),
        "duplicate_signer": lambda: scheme.combine([shares[0], shares[0]], config["round_id"], config["dlog_bound"]),
        "tampered_numerator": lambda: scheme.combine(
            [shares[0], scheme.tamper_numerator(shares[1])], config["round_id"], config["dlog_bound"]
        ),
        "replay": lambda: scheme.share_decrypt(
            ciphertexts, config["weights"], keys[config["committee"][0]], config["committee"],
            config["round_id"] + 1,
        ),
    }
    for name, operation in cases.items():
        try:
            operation()
        except TMCFEError as exc:
            negative_checks[name] = {"rejected": True, "reason": str(exc)}
        else:
            negative_checks[name] = {"rejected": False, "reason": None}

    result = {
        "run_id": config["run_id"],
        "status": "passed" if recovered == expected and all(x["rejected"] for x in negative_checks.values()) else "failed",
        "group": config["group"],
        "expected": expected,
        "recovered": recovered,
        "exact_match": recovered == expected,
        "negative_checks": negative_checks,
        "ciphertext_bytes_per_client": [scheme.serialized_size(item) for item in ciphertexts],
        "partial_share_bytes": [scheme.serialized_size(item) for item in shares],
        "wall_seconds": time.perf_counter() - start,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

