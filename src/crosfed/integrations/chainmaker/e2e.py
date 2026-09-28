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
def digest(value: bytes) -> str:
    return "0x" + hashlib.sha256(value).hexdigest()


def hex_bytes(value: bytes) -> str:
    return "0x" + value.hex()


def find_metric(value: Any, names: set[str]) -> int | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower().replace("_", "") in names:
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


def find_request_id(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower().replace("_", "") in {"requestid", "contractresult"}:
                candidate = str(item)
                if candidate.startswith("0x") and len(candidate) == 66:
                    return candidate
            found = find_request_id(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_request_id(item)
            if found:
                return found
    return None


def timed_call(call, *args) -> dict:
    started = time.perf_counter()
    response = dict(call(*args))
    response["wall_seconds"] = time.perf_counter() - started
    response["transaction_gas"] = find_metric(response, {"transactiongas", "txgas", "gasused"})
    response["execution_gas"] = find_metric(response, {"executiongas", "contractgas"})
    return response


def exercise_flow(client, registry: dict, relay: dict, relay_contract: str,
                  request_method: str, fulfill_method: str, response_method: str,
                  kind: str, payload: bytes, round_digest: str) -> dict:
    timestamp = str(time.time_ns())
    signature = hex_bytes(secrets.token_bytes(64))
    common = {
        "roundContextDigest": round_digest,
        "signerId": "crosfed-e2e",
        "payload": hex_bytes(payload),
        "payloadDigest": digest(payload),
        "signature": signature,
        "timestampNs": timestamp,
        "transactionHash": digest(secrets.token_bytes(32)),
        "kind": kind,
        "schemaVersion": "1",
    }
    upload = timed_call(client.invoke_contract, registry["chain_id"], registry["contract"], registry["submit_method"], common)
    query = timed_call(client.query_contract, registry["chain_id"], registry["contract"], registry["query_method"], {"roundContextDigest": round_digest})
    request = timed_call(client.invoke_contract, relay["chain_id"], relay_contract, request_method, {
        "roundContextDigest": round_digest,
        "targetChain": registry["chain_id"],
        "requestSignature": signature,
        "timestampNs": str(time.time_ns()),
    })
    request_id = find_request_id(request)
    if request_id is None:
        raise RuntimeError(
            "CMC output did not expose the bytes32 relay requestId; configure ABI-decoded "
            "return values for this ChainMaker/CMC version"
        )
    response_payload = json.dumps(query, sort_keys=True, separators=(",", ":")).encode()
    fulfill = timed_call(client.invoke_contract, relay["chain_id"], relay_contract, fulfill_method, {
        "requestId": request_id,
        "responsePayload": hex_bytes(response_payload),
        "responseDigest": digest(response_payload),
        "responseSignature": hex_bytes(secrets.token_bytes(64)),
        "timestampNs": str(time.time_ns()),
    })
    response = timed_call(client.query_contract, relay["chain_id"], relay_contract, response_method, {"requestId": request_id})
    return {"upload": upload, "registry_query": query, "relay_request": request,
            "request_id": request_id, "relay_fulfill": fulfill, "relay_response": response,
            "response_payload_bytes": len(response_payload)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run both CrosFed ChainMaker cross-chain flows")
    parser.add_argument("--config", required=True)
    parser.add_argument("--payload-bytes", type=int, default=1024)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.payload_bytes <= 0:
        raise ValueError("payload-bytes must be positive")
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    bridge = config["sdk_bridge"]
    client = SubprocessChainMakerClient(
        [str(item) for item in bridge["command"]], float(bridge.get("timeout_seconds", 120))
    )
    payload = secrets.token_bytes(args.payload_bytes)
    round_digest = digest(f"crosfed-e2e:{time.time_ns()}".encode())
    relay = config["relay"]
    result = {"status": "running", "config": args.config, "round_context_digest": round_digest,
              "payload_bytes": args.payload_bytes}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["encrypted_update_flow"] = exercise_flow(
        client, config["institution_chain"], relay, relay["encrypted_update_contract"],
        "requestEncryptedLocalUpdates", "fulfillEncryptedLocalUpdates",
        "getEncryptedLocalUpdateResponse", "encrypted_local_update", payload, round_digest,
    )
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["partial_update_flow"] = exercise_flow(
        client, config["aggregator_chain"], relay, relay["partial_update_contract"],
        "requestPartialGlobalUpdates", "fulfillPartialGlobalUpdates",
        "getPartialGlobalUpdateResponse", "partial_global_update", payload, round_digest,
    )
    result["status"] = "passed"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
