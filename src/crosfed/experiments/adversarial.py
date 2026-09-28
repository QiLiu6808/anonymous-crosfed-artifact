from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Callable

from crosfed.crypto import TMCFEError, ThresholdMCFE


def expect_rejection(name: str, action: Callable[[], object]) -> dict:
    try:
        action()
    except (TMCFEError, ValueError) as exc:
        return {"case": name, "status": "passed", "rejected": True, "reason": str(exc)}
    return {"case": name, "status": "failed", "rejected": False, "reason": None}


def run_suite(group: str = "SS512") -> dict:
    vectors = [[3, -2, 5], [-1, 4, 2], [2, 1, -4]]
    weights = [[1, 1, 1], [2, 2, 2], [1, 1, 1]]
    scheme = ThresholdMCFE(group)
    scheme.setup(clients=3, dimension=3)
    keys = scheme.generate_functional_keys(weights, [1, 2, 3], threshold=2, round_id=7)
    ciphertexts = [
        scheme.encrypt(vector, scheme.encryption_key(index), 7)
        for index, vector in enumerate(vectors, start=1)
    ]
    shares = [
        scheme.share_decrypt(ciphertexts, weights, keys[index], [1, 2, 3], 7)
        for index in [1, 2, 3]
    ]
    expected = [
        sum(vectors[i][z] * weights[i][z] for i in range(3)) for z in range(3)
    ]
    recovered = scheme.combine(shares[:2], 7, 64)
    malicious_weights = [row[:] for row in weights]
    malicious_weights[0][0] += 1
    replayed_ciphertexts = list(ciphertexts)
    replayed_ciphertexts[0] = scheme.encrypt(vectors[0], scheme.encryption_key(1), 6)
    cases = [
        expect_rejection("threshold_minus_one", lambda: scheme.combine(shares[:1], 7, 64)),
        expect_rejection("duplicate_signer", lambda: scheme.combine([shares[0], shares[0]], 7, 64)),
        expect_rejection(
            "outsider_signer",
            lambda: scheme.combine([shares[0], replace(shares[1], aggregator_id=99)], 7, 64),
        ),
        expect_rejection(
            "tampered_numerator",
            lambda: scheme.combine([shares[0], scheme.tamper_numerator(shares[1])], 7, 64),
        ),
        expect_rejection(
            "wrong_function_weights",
            lambda: scheme.share_decrypt(ciphertexts, malicious_weights, keys[1], [1, 2, 3], 7),
        ),
        expect_rejection(
            "replayed_ciphertext",
            lambda: scheme.share_decrypt(replayed_ciphertexts, weights, keys[1], [1, 2, 3], 7),
        ),
        expect_rejection(
            "mixed_round_share",
            lambda: scheme.combine([shares[0], replace(shares[1], round_id=8)], 7, 64),
        ),
    ]
    passed = recovered == expected and all(case["status"] == "passed" for case in cases)
    return {
        "status": "passed" if passed else "failed",
        "group": group,
        "positive_control": {
            "expected": expected,
            "recovered": recovered,
            "exact_oracle_match": recovered == expected,
        },
        "negative_cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CrosFed adversarial protocol checks")
    parser.add_argument("--group", default="SS512")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_suite(args.group)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
