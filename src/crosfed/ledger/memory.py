from __future__ import annotations

import json
import threading
import uuid
from collections import defaultdict

from crosfed.domain import MessageKind, SignedEnvelope, canonical_json
from crosfed.domain.messages import EnvelopeSigner

from .ports import CommitReceipt


class InMemoryLedger:
    """Deterministic ledger adapter that executes the contract validation rules."""

    def __init__(self, chain_id: str, signer: EnvelopeSigner) -> None:
        self.chain_id = chain_id
        self._signer = signer
        self._lock = threading.RLock()
        self._records: dict[tuple[MessageKind, str], dict[str, SignedEnvelope]] = defaultdict(dict)

    def commit(self, envelope: SignedEnvelope) -> CommitReceipt:
        if not envelope.verify(self._signer):
            raise ValueError("invalid envelope signature, digest, or transaction hash")
        key = (envelope.kind, envelope.round_context_digest)
        with self._lock:
            signers = self._records[key]
            if envelope.signer_id in signers:
                raise ValueError("duplicate signer submission for round and message kind")
            signers[envelope.signer_id] = envelope
        wire_bytes = len(canonical_json(envelope.to_dict()))
        return CommitReceipt(
            self.chain_id,
            str(uuid.uuid4()),
            envelope.transaction_hash,
            True,
            wire_bytes,
        )

    def query_round(
        self, kind: MessageKind, round_context_digest: str
    ) -> list[SignedEnvelope]:
        with self._lock:
            records = list(self._records.get((kind, round_context_digest), {}).values())
        records.sort(key=lambda envelope: envelope.signer_id)
        if any(not record.verify(self._signer) for record in records):
            raise ValueError("ledger contains an invalid envelope")
        return records


class InMemoryRelay:
    """Routing adapter with an explicit allow-list of source/target chains."""

    def __init__(self, ledgers: list[InMemoryLedger]) -> None:
        self._ledgers = {ledger.chain_id: ledger for ledger in ledgers}
        self.audit_log: list[dict[str, str | int]] = []

    def query(
        self,
        source_chain: str,
        target_chain: str,
        kind: MessageKind,
        round_context_digest: str,
    ) -> list[SignedEnvelope]:
        if source_chain not in self._ledgers:
            raise KeyError(f"unknown source chain: {source_chain}")
        target = self._ledgers.get(target_chain)
        if target is None:
            raise KeyError(f"unknown target chain: {target_chain}")
        records = target.query_round(kind, round_context_digest)
        self.audit_log.append(
            {
                "source_chain": source_chain,
                "target_chain": target_chain,
                "kind": kind.value,
                "round_context_digest": round_context_digest,
                "records": len(records),
            }
        )
        return records

