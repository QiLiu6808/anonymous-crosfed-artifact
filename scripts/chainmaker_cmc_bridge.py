from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


def _last_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    candidates: list[tuple[int, dict[str, Any]]] = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, consumed = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append((consumed, value))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _find_first(value: Any, keys: set[str]) -> Any | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower().replace("_", "") in keys:
                return item
        for item in value.values():
            found = _find_first(item, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_first(item, keys)
            if found is not None:
                return found
    return None


def _lookup(record: dict[str, Any], name: str) -> Any | None:
    normalized = name.lower().replace("_", "")
    for key, value in record.items():
        if key.lower().replace("_", "") == normalized:
            return value
    return None


def _hex_to_text(value: Any) -> str:
    if isinstance(value, list) and all(isinstance(item, int) for item in value):
        return bytes(value).decode("utf-8")
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8")
    text = str(value)
    if text.startswith("0x"):
        return bytes.fromhex(text[2:]).decode("utf-8")
    return text


def _strip_hex_prefix(value: Any) -> str:
    if isinstance(value, list) and all(isinstance(item, int) for item in value):
        return bytes(value).hex()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    text = str(value)
    return text[2:] if text.startswith("0x") else text


def _evm_arguments(arguments: dict[str, Any]) -> dict[str, str]:
    encoded: dict[str, str] = {}
    bytes_fields = {"payload", "signature", "requestSignature", "responsePayload", "responseSignature"}
    bytes32_fields = {"roundContextDigest", "payloadDigest", "transactionHash", "requestId", "responseDigest"}
    for key, value in arguments.items():
        text = str(value)
        if key in bytes_fields and not text.startswith("0x"):
            if key == "signature" and re.fullmatch(r"[0-9a-fA-F]+", text) and len(text) % 2 == 0:
                text = "0x" + text
            else:
                text = "0x" + text.encode("utf-8").hex()
        elif key in bytes32_fields and not text.startswith("0x"):
            text = "0x" + text
        encoded[key] = text
    return encoded


def _record_to_envelope(record: dict[str, Any]) -> dict[str, Any] | None:
    required = {
        "signer_id": _lookup(record, "signerId"),
        "kind": _lookup(record, "kind"),
        "schema_version": _lookup(record, "schemaVersion"),
        "round_context_digest": _lookup(record, "roundContextDigest"),
        "payload": _lookup(record, "payload"),
        "payload_digest": _lookup(record, "payloadDigest"),
        "signature": _lookup(record, "signature"),
        "timestamp_ns": _lookup(record, "timestampNs"),
        "transaction_hash": _lookup(record, "transactionHash"),
    }
    if any(value is None for value in required.values()):
        return None
    return {
        "signer_id": str(required["signer_id"]),
        "kind": str(required["kind"]),
        "schema_version": int(required["schema_version"]),
        "round_context_digest": _strip_hex_prefix(required["round_context_digest"]),
        "payload": json.loads(_hex_to_text(required["payload"])),
        "payload_digest": _strip_hex_prefix(required["payload_digest"]),
        "signature": _strip_hex_prefix(required["signature"]),
        "timestamp_ns": int(required["timestamp_ns"]),
        "transaction_hash": _strip_hex_prefix(required["transaction_hash"]),
    }


def _normalized_envelopes(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    existing = _find_first(parsed, {"envelopes"})
    if isinstance(existing, list):
        return existing
    candidates = _find_first(parsed, {"records", "result", "contractresult"})
    if isinstance(candidates, dict):
        candidates = [candidates]
    if not isinstance(candidates, list):
        return []
    envelopes = []
    for candidate in candidates:
        if isinstance(candidate, dict):
            envelope = _record_to_envelope(candidate)
            if envelope is not None:
                envelopes.append(envelope)
    return envelopes


def _transaction_id(parsed: dict[str, Any] | None, raw: str) -> str:
    value = _find_first(parsed, {"txid", "transactionid"}) if parsed else None
    if value is not None:
        return str(value)
    match = re.search(r"(?:tx[_ ]?id|transaction[_ ]?id)\s*[:=]\s*[\"']?([\w.-]+)", raw, re.I)
    if match:
        return match.group(1)
    raise RuntimeError("cmc output did not contain a transaction id")


def _run(request: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    cmc = config["cmc"]
    operation = request["operation"]
    action = cmc["invoke_action"] if operation == "invoke" else cmc["query_action"]
    sdk_path = cmc["sdk_conf_by_chain"].get(request["chain_id"])
    if not sdk_path:
        raise ValueError(f"no sdk config for chain {request['chain_id']}")
    command = [
        str(cmc["executable"]),
        "client",
        "contract",
        "user",
        str(action),
        "--contract-name",
        str(request["contract"]),
        "--method",
        str(request["method"]),
        "--sdk-conf-path",
        str(sdk_path),
        "--params",
        json.dumps(_evm_arguments(dict(request.get("arguments", {}))), separators=(",", ":")),
    ]
    abi_path = cmc.get("abi_file_by_contract", {}).get(request["contract"])
    if abi_path:
        command.extend(["--abi-file-path", str(abi_path)])
    if operation == "invoke" and cmc.get("sync_result", True):
        command.append("--sync-result=true")
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    raw = completed.stdout.strip()
    if completed.returncode != 0:
        raise RuntimeError(f"cmc exited {completed.returncode}: {completed.stderr.strip() or raw}")
    parsed = _last_json_object(raw)
    if operation == "invoke":
        return {
            "transaction_id": _transaction_id(parsed, raw),
            "accepted": True,
            "cmc_result": parsed,
        }
    if parsed is None:
        raise RuntimeError("cmc query output did not contain JSON")
    envelopes = _normalized_envelopes(parsed)
    if not envelopes:
        raise RuntimeError("cmc query did not contain ABI-decoded signed envelopes")
    return {"envelopes": envelopes, "cmc_result": parsed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    request = json.load(sys.stdin)
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    try:
        response = _run(request, config)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    json.dump(response, sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
