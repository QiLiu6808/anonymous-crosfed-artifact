from __future__ import annotations

from collections import OrderedDict

import torch

from crosfed.crypto import FixedPointCodec
from crosfed.domain import RoundPhase
from crosfed.orchestration import SecureRoundOrchestrator


def test_secure_round_matches_integer_oracle() -> None:
    template = OrderedDict(weight=torch.tensor([0.0, 0.0]))
    orchestrator = SecureRoundOrchestrator(
        "test", template, clients=2, aggregators=3, threshold=2,
        codec=FixedPointCodec(scale=100, clip=8),
    )
    result = orchestrator.aggregate(
        [
            OrderedDict(weight=torch.tensor([1.0, -2.0])),
            OrderedDict(weight=torch.tensor([3.0, 2.0])),
        ],
        [1, 3],
        round_id=1,
        committee=[1, 3],
        dlog_bound=2_000,
    )
    assert result.exact_oracle_match
    assert result.phase == RoundPhase.GLOBAL_DECRYPTED
    assert torch.allclose(result.global_state["weight"], torch.tensor([2.5, 1.0]))
