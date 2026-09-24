from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class FixedPointCodec:
    """Deterministic signed fixed-point encoding with explicit clipping."""

    scale: int = 1_000
    clip: float = 8.0

    def __post_init__(self) -> None:
        if self.scale <= 0:
            raise ValueError("scale must be positive")
        if self.clip <= 0:
            raise ValueError("clip must be positive")

    @property
    def encoded_bound(self) -> int:
        return round(self.scale * self.clip)

    def encode(self, values: Iterable[float]) -> list[int]:
        result: list[int] = []
        for value in values:
            clipped = min(self.clip, max(-self.clip, float(value)))
            result.append(round(clipped * self.scale))
        return result

    def decode(self, values: Iterable[int]) -> list[float]:
        return [int(value) / self.scale for value in values]

