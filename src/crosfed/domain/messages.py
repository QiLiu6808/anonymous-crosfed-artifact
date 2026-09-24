from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Protocol


SCHEMA_VERSION = 1


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class MessageKind(str, Enum):
    ENCRYPTED_LOCAL_UPDATE = "encrypted_local_update"
    PARTIAL_GLOBAL_UPDATE = "partial_global_update"


@dataclass(frozen=True)
class RoundContext:
    experiment_id: str
    round_id: int
    clients: int
    aggregators: int
    threshold: int
    committee: tuple[int, ...]
    model_digest: str
    codec_id: str
    function_digest: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported round-context schema")
        if self.round_id < 0:
            raise ValueError("round_id must be non-negative")
        if self.clients <= 0 or self.aggregators <= 0:
            raise ValueError("clients and aggregators must be positive")
        if not 1 <= self.threshold <= self.aggregators:
            raise ValueError("invalid threshold")
        if len(set(self.committee)) != len(self.committee):
            raise ValueError("committee identities must be unique")
        if len(self.committee) < self.threshold:
            raise ValueError("committee cannot be smaller than threshold")
        if any(identity < 1 or identity > self.aggregators for identity in self.committee):
            raise ValueError("committee identity out of range")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["committee"] = list(self.committee)
        return value

    @property
    def digest(self) -> str:
        return sha256_hex(canonical_json(self.to_dict()))


class EnvelopeSigner(Protocol):
    def sign(self, signer_id: str, message: bytes) -> str: ...
    def verify(self, signer_id: str, message: bytes, signature: str) -> bool: ...


@dataclass(frozen=True)
class SignedEnvelope:
    kind: MessageKind
    signer_id: str
    round_context_digest: str
    payload: Mapping[str, Any]
    timestamp_ns: int
    payload_digest: str
    signature: str
    transaction_hash: str
    schema_version: int = SCHEMA_VERSION

    @staticmethod
    def _unsigned_dict(
        kind: MessageKind,
        signer_id: str,
        round_context_digest: str,
        payload: Mapping[str, Any],
        timestamp_ns: int,
    ) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": kind.value,
            "signer_id": signer_id,
            "round_context_digest": round_context_digest,
            "payload": payload,
            "timestamp_ns": timestamp_ns,
            "payload_digest": sha256_hex(canonical_json(payload)),
        }

    @classmethod
    def create(
        cls,
        kind: MessageKind,
        signer_id: str,
        round_context: RoundContext,
        payload: Mapping[str, Any],
        signer: EnvelopeSigner,
        timestamp_ns: int | None = None,
    ) -> "SignedEnvelope":
        timestamp = time.time_ns() if timestamp_ns is None else int(timestamp_ns)
        unsigned = cls._unsigned_dict(
            kind, signer_id, round_context.digest, payload, timestamp
        )
        unsigned_bytes = canonical_json(unsigned)
        signature = signer.sign(signer_id, unsigned_bytes)
        transaction_hash = sha256_hex(
            canonical_json({**unsigned, "signature": signature})
        )
        return cls(
            kind=kind,
            signer_id=signer_id,
            round_context_digest=round_context.digest,
            payload=payload,
            timestamp_ns=timestamp,
            payload_digest=unsigned["payload_digest"],
            signature=signature,
            transaction_hash=transaction_hash,
        )

    def verify(self, signer: EnvelopeSigner) -> bool:
        if self.schema_version != SCHEMA_VERSION:
            return False
        unsigned = self._unsigned_dict(
            self.kind,
            self.signer_id,
            self.round_context_digest,
            self.payload,
            self.timestamp_ns,
        )
        if unsigned["payload_digest"] != self.payload_digest:
            return False
        if not signer.verify(self.signer_id, canonical_json(unsigned), self.signature):
            return False
        expected_hash = sha256_hex(
            canonical_json({**unsigned, "signature": self.signature})
        )
        return expected_hash == self.transaction_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "signer_id": self.signer_id,
            "round_context_digest": self.round_context_digest,
            "payload": self.payload,
            "timestamp_ns": self.timestamp_ns,
            "payload_digest": self.payload_digest,
            "signature": self.signature,
            "transaction_hash": self.transaction_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SignedEnvelope":
        return cls(
            kind=MessageKind(value["kind"]),
            signer_id=str(value["signer_id"]),
            round_context_digest=str(value["round_context_digest"]),
            payload=dict(value["payload"]),
            timestamp_ns=int(value["timestamp_ns"]),
            payload_digest=str(value["payload_digest"]),
            signature=str(value["signature"]),
            transaction_hash=str(value["transaction_hash"]),
            schema_version=int(value["schema_version"]),
        )
