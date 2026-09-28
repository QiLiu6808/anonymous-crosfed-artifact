from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class QuantizationDiagnostics:
    count: int
    max_abs: float
    clipped_count: int
    saturated_count: int
    encoded_abs_max: int
    encoded_bound: int

    @property
    def clipped_fraction(self) -> float:
        return self.clipped_count / self.count if self.count else 0.0

    @property
    def bound_utilization(self) -> float:
        return self.encoded_abs_max / self.encoded_bound if self.encoded_bound else 0.0

    def to_dict(self) -> dict[str, int | float]:
        return {
            "count": self.count,
            "max_abs": self.max_abs,
            "clipped_count": self.clipped_count,
            "clipped_fraction": self.clipped_fraction,
            "saturated_count": self.saturated_count,
            "encoded_abs_max": self.encoded_abs_max,
            "encoded_bound": self.encoded_bound,
            "bound_utilization": self.bound_utilization,
        }


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
        encoded, _ = self.encode_with_diagnostics(values)
        return encoded

    def encode_with_diagnostics(
        self, values: Iterable[float]
    ) -> tuple[list[int], QuantizationDiagnostics]:
        result: list[int] = []
        count = 0
        max_abs = 0.0
        clipped_count = 0
        for value in values:
            numeric = float(value)
            magnitude = abs(numeric)
            count += 1
            max_abs = max(max_abs, magnitude)
            if magnitude > self.clip:
                clipped_count += 1
            clipped = min(self.clip, max(-self.clip, numeric))
            result.append(round(clipped * self.scale))
        encoded_abs_max = max((abs(value) for value in result), default=0)
        diagnostics = QuantizationDiagnostics(
            count=count,
            max_abs=max_abs,
            clipped_count=clipped_count,
            saturated_count=sum(
                abs(value) == self.encoded_bound for value in result
            ),
            encoded_abs_max=encoded_abs_max,
            encoded_bound=self.encoded_bound,
        )
        return result, diagnostics

    def decode(self, values: Iterable[int]) -> list[float]:
        return [int(value) / self.scale for value in values]
