from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crosfed.domain import MessageKind, SignedEnvelope


@dataclass(frozen=True)
class CommitReceipt:
    chain_id: str
    transaction_id: str
    transaction_hash: str
    accepted: bool
    wire_bytes: int


class LedgerPort(Protocol):
    chain_id: str

    def commit(self, envelope: SignedEnvelope) -> CommitReceipt: ...

    def query_round(
        self, kind: MessageKind, round_context_digest: str
    ) -> list[SignedEnvelope]: ...


class RelayPort(Protocol):
    def query(
        self,
        source_chain: str,
        target_chain: str,
        kind: MessageKind,
        round_context_digest: str,
    ) -> list[SignedEnvelope]: ...

