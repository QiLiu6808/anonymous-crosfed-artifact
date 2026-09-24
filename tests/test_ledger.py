from __future__ import annotations

import pytest

from crosfed.crypto import HMACSignatureProvider
from crosfed.domain import MessageKind, RoundContext, SignedEnvelope
from crosfed.ledger import ChainMakerLedger, InMemoryLedger, InMemoryRelay


def make_envelope() -> tuple[SignedEnvelope, HMACSignatureProvider]:
    signer = HMACSignatureProvider({"institution:1": b"k" * 32})
    context = RoundContext("test", 1, 1, 1, 1, (1,), "model", "codec", "function")
    envelope = SignedEnvelope.create(
        MessageKind.ENCRYPTED_LOCAL_UPDATE,
        "institution:1",
        context,
        {"ct0": ["abc"]},
        signer,
        timestamp_ns=123,
    )
    return envelope, signer


def test_memory_ledger_and_relay_enforce_duplicate_rule() -> None:
    envelope, signer = make_envelope()
    source = InMemoryLedger("source", signer)
    target = InMemoryLedger("target", signer)
    target.commit(envelope)
    with pytest.raises(ValueError, match="duplicate"):
        target.commit(envelope)
    relay = InMemoryRelay([source, target])
    assert relay.query("source", "target", envelope.kind, envelope.round_context_digest) == [envelope]


class FakeChainMakerClient:
    def __init__(self, envelope: SignedEnvelope) -> None:
        self.envelope = envelope
        self.arguments = None

    def invoke_contract(self, chain_id, contract, method, arguments):
        self.arguments = arguments
        return {"transaction_id": "tx-1", "accepted": True}

    def query_contract(self, chain_id, contract, method, arguments):
        return {"envelopes": [self.envelope.to_dict()]}


def test_chainmaker_adapter_maps_envelope_fields() -> None:
    envelope, _ = make_envelope()
    client = FakeChainMakerClient(envelope)
    ledger = ChainMakerLedger("chain", "registry", client, "submit", "query")
    receipt = ledger.commit(envelope)
    assert receipt.transaction_id == "tx-1"
    assert client.arguments["roundContextDigest"] == envelope.round_context_digest
    assert client.arguments["payloadDigest"] == envelope.payload_digest
    assert ledger.query_round(envelope.kind, envelope.round_context_digest) == [envelope]
