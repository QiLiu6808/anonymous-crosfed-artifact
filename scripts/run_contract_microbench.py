from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any, Mapping

import yaml

from crosfed.ledger import SubprocessChainMakerClient


def hex_bytes(value: bytes) -> str:
    return "0x" + value.hex()


def digest(value: bytes) -> str:
    return "0x" + hashlib.sha256(value).hexdigest()


def find_metric(value: Any, names: set[str]) -> int | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower().replace("_", "")
            if normalized in names:
                try:
                    return int(item)
                except (TypeError, ValueError):
                    pass
        for item in value.values():
            result = find_metric(item, names)
            if result is not None:
                return result
    elif isinstance(value, list):
        for item in value:
            result = find_metric(item, names)
            if result is not None:
                return result
    return None


def invoke(client, chain_id: str, contract: str, method: str, arguments: dict[str, str]) -> dict:
    started = time.perf_counter()
    response = dict(client.invoke_contract(chain_id, contract, method, arguments))
    response["wall_seconds"] = time.perf_counter() - started
    response["transaction_gas"] = find_metric(response, {"transactiongas", "txgas", "gasused"})
    response["execution_gas"] = find_metric(response, {"executiongas", "contractgas"})
    return response


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="chainmaker/config/example.yaml")
    parser.add_argument("--payload-bytes", type=int, default=1024)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.payload_bytes <= 0 or args.repetitions <= 0:
        raise ValueError("payload bytes and repetitions must be positive")
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    bridge = config["sdk_bridge"]
    client = SubprocessChainMakerClient(
        [str(item) for item in bridge["command"]],
        float(bridge.get("timeout_seconds", 120)),
    )
    institution = config["institution_chain"]
    aggregator = config["aggregator_chain"]
    relay = config["relay"]
    records = []
    for repetition in range(1, args.repetitions + 1):
        payload = secrets.token_bytes(args.payload_bytes)
        round_digest = digest(f"microbench:{repetition}:{time.time_ns()}".encode())
        timestamp = str(time.time_ns())
        common = {
            "roundContextDigest": round_digest,
            "signerId": "microbench",
            "payload": hex_bytes(payload),
            "payloadDigest": digest(payload),
            "signature": hex_bytes(secrets.token_bytes(64)),
            "timestampNs": timestamp,
            "transactionHash": digest(secrets.token_bytes(32)),
            "schemaVersion": "1",
        }
        encrypted_upload = invoke(
            client, institution["chain_id"], institution["contract"],
            institution["submit_method"], {**common, "kind": "encrypted_local_update"},
        )
        partial_upload = invoke(
            client, aggregator["chain_id"], aggregator["contract"],
            aggregator["submit_method"], {**common, "kind": "partial_global_update"},
        )
        encrypted_request = invoke(
            client, relay["chain_id"], relay["encrypted_update_contract"],
            "requestEncryptedLocalUpdates",
            {
                "roundContextDigest": round_digest,
                "targetChain": institution["chain_id"],
                "requestSignature": common["signature"],
                "timestampNs": timestamp,
            },
        )
        partial_request = invoke(
            client, relay["chain_id"], relay["partial_update_contract"],
            "requestPartialGlobalUpdates",
            {
                "roundContextDigest": round_digest,
                "targetChain": aggregator["chain_id"],
                "requestSignature": common["signature"],
                "timestampNs": timestamp,
            },
        )
        records.append(
            {
                "repetition": repetition,
                "payload_bytes": args.payload_bytes,
                "upload_encrypted": encrypted_upload,
                "download_encrypted_request": encrypted_request,
                "upload_partial": partial_upload,
                "download_partial_request": partial_request,
            }
        )
        output = {
            "status": "running",
            "config": args.config,
            "payload_bytes": args.payload_bytes,
            "records": records,
        }
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    output["status"] = "passed"
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
