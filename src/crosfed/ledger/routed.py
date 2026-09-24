from __future__ import annotations

from crosfed.domain import MessageKind, SignedEnvelope

from .ports import LedgerPort


class RoutedRelay:
    """Allow-listed relay over arbitrary ledger adapters.

    For the in-memory backend this is a direct call.  For ChainMaker, each
    target ledger delegates the query to its configured SDK/CMC bridge.
    """

    def __init__(
        self,
        ledgers: list[LedgerPort],
        allowed_routes: set[tuple[str, str]] | None = None,
    ) -> None:
        self._ledgers = {ledger.chain_id: ledger for ledger in ledgers}
        self._allowed_routes = allowed_routes or {
            (source, target)
            for source in self._ledgers
            for target in self._ledgers
            if source != target
        }
        self.audit_log: list[dict[str, str | int]] = []

    def query(
        self,
        source_chain: str,
        target_chain: str,
        kind: MessageKind,
        round_context_digest: str,
    ) -> list[SignedEnvelope]:
        if (source_chain, target_chain) not in self._allowed_routes:
            raise PermissionError(f"relay route is not allowed: {source_chain} -> {target_chain}")
        if target_chain not in self._ledgers:
            raise KeyError(f"unknown target chain: {target_chain}")
        records = self._ledgers[target_chain].query_round(kind, round_context_digest)
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
