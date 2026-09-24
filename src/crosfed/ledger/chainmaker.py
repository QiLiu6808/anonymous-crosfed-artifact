from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from crosfed.domain import EnvelopeSigner, MessageKind, SignedEnvelope, canonical_json

from .ports import CommitReceipt


class ChainMakerClient(Protocol):
    """Minimal boundary implemented by a concrete ChainMaker SDK binding."""

    def invoke_contract(
        self, chain_id: str, contract: str, method: str, arguments: Mapping[str, str]
    ) -> Mapping[str, Any]: ...

    def query_contract(
        self, chain_id: str, contract: str, method: str, arguments: Mapping[str, str]
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class SubprocessChainMakerClient:
    """Concrete bridge to a version-specific ChainMaker SDK wrapper.

    The wrapper command receives one JSON request on stdin and must emit one JSON
    object on stdout. Keeping the SDK out of the experiment process makes the
    Python/Go ChainMaker version independently replaceable.
    """

    command: Sequence[str]
    timeout_seconds: float = 120.0

    def _call(self, operation: str, request: Mapping[str, Any]) -> Mapping[str, Any]:
        completed = subprocess.run(
            list(self.command),
            input=json.dumps({"operation": operation, **request}),
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"ChainMaker bridge failed ({completed.returncode}): {completed.stderr.strip()}"
            )
        response = json.loads(completed.stdout)
        if not isinstance(response, dict):
            raise RuntimeError("ChainMaker bridge response must be a JSON object")
        return response

    def invoke_contract(
        self, chain_id: str, contract: str, method: str, arguments: Mapping[str, str]
    ) -> Mapping[str, Any]:
        return self._call(
            "invoke",
            {"chain_id": chain_id, "contract": contract, "method": method, "arguments": arguments},
        )

    def query_contract(
        self, chain_id: str, contract: str, method: str, arguments: Mapping[str, str]
    ) -> Mapping[str, Any]:
        return self._call(
            "query",
            {"chain_id": chain_id, "contract": contract, "method": method, "arguments": arguments},
        )


class ChainMakerLedger:
    """LedgerPort implementation independent of a particular ChainMaker SDK version."""

    def __init__(
        self,
        chain_id: str,
        contract: str,
        client: ChainMakerClient,
        submit_method: str,
        query_method: str,
        verifier: EnvelopeSigner | None = None,
    ) -> None:
        self.chain_id = chain_id
        self.contract = contract
        self.client = client
        self.submit_method = submit_method
        self.query_method = query_method
        self.verifier = verifier

    def commit(self, envelope: SignedEnvelope) -> CommitReceipt:
        encoded_payload = canonical_json(envelope.payload)
        response = self.client.invoke_contract(
            self.chain_id,
            self.contract,
            self.submit_method,
            {
                "roundContextDigest": envelope.round_context_digest,
                "signerId": envelope.signer_id,
                "payload": encoded_payload.decode("utf-8"),
                "payloadDigest": envelope.payload_digest,
                "signature": envelope.signature,
                "timestampNs": str(envelope.timestamp_ns),
                "transactionHash": envelope.transaction_hash,
                "kind": envelope.kind.value,
                "schemaVersion": str(envelope.schema_version),
            },
        )
        encoded_envelope = canonical_json(envelope.to_dict())
        return CommitReceipt(
            chain_id=self.chain_id,
            transaction_id=str(response["transaction_id"]),
            transaction_hash=envelope.transaction_hash,
            accepted=bool(response.get("accepted", True)),
            wire_bytes=len(encoded_envelope),
        )

    def query_round(
        self, kind: MessageKind, round_context_digest: str
    ) -> list[SignedEnvelope]:
        response = self.client.query_contract(
            self.chain_id,
            self.contract,
            self.query_method,
            {"roundContextDigest": round_context_digest},
        )
        records = response.get("envelopes", [])
        envelopes = [
            SignedEnvelope.from_dict(record if isinstance(record, dict) else json.loads(record))
            for record in records
        ]
        if any(
            envelope.kind != kind
            or envelope.round_context_digest != round_context_digest
            for envelope in envelopes
        ):
            raise ValueError("ChainMaker query returned an envelope from another context")
        if self.verifier is not None and any(
            not envelope.verify(self.verifier) for envelope in envelopes
        ):
            raise ValueError("ChainMaker query returned an invalid signed envelope")
        return envelopes
