from __future__ import annotations

from dataclasses import replace

import pytest

from crosfed.crypto import HMACSignatureProvider
from crosfed.domain import MessageKind, RoundContext, RoundPhase, RoundStateMachine, SignedEnvelope


def context() -> RoundContext:
    return RoundContext("test", 1, 2, 3, 2, (1, 3), "model", "codec", "function")


def test_signed_envelope_roundtrip_and_tamper_detection() -> None:
    signer = HMACSignatureProvider({"institution:1": b"a" * 32})
    envelope = SignedEnvelope.create(
        MessageKind.ENCRYPTED_LOCAL_UPDATE,
        "institution:1",
        context(),
        {"ciphertext": "abc"},
        signer,
        timestamp_ns=123,
    )
    restored = SignedEnvelope.from_dict(envelope.to_dict())
    assert restored.verify(signer)
    assert not replace(restored, payload={"ciphertext": "changed"}).verify(signer)


def test_round_state_machine_rejects_skips() -> None:
    machine = RoundStateMachine()
    machine.advance(RoundPhase.LOCAL_TRAINED)
    with pytest.raises(ValueError, match="invalid round transition"):
        machine.advance(RoundPhase.ENCRYPTED)


def test_round_context_rejects_out_of_range_committee() -> None:
    with pytest.raises(ValueError, match="out of range"):
        RoundContext("test", 1, 2, 2, 1, (3,), "model", "codec", "function")
