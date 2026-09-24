from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class RoundPhase(IntEnum):
    ROUND_CREATED = 0
    LOCAL_TRAINED = 1
    ENCODED = 2
    ENCRYPTED = 3
    LOCAL_UPDATES_COMMITTED = 4
    COMMITTEE_FROZEN = 5
    SHARES_COMPUTED = 6
    SHARES_COMMITTED = 7
    THRESHOLD_REACHED = 8
    GLOBAL_DECRYPTED = 9
    EVALUATED = 10
    ROUND_FINALIZED = 11


@dataclass
class RoundStateMachine:
    phase: RoundPhase = RoundPhase.ROUND_CREATED

    def advance(self, target: RoundPhase) -> None:
        if int(target) != int(self.phase) + 1:
            raise ValueError(f"invalid round transition: {self.phase.name} -> {target.name}")
        self.phase = target

    def require_at_least(self, phase: RoundPhase) -> None:
        if self.phase < phase:
            raise ValueError(f"round is at {self.phase.name}, requires {phase.name}")

