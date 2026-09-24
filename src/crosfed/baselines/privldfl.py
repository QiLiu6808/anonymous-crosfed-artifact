from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from functools import reduce
from typing import Sequence

import torch

from crosfed.crypto import FixedPointCodec
from crosfed.ml import flatten_state_dict, unflatten_state_dict


def _is_prime(value: int) -> bool:
    if value < 2:
        return False
    if value % 2 == 0:
        return value == 2
    divisor = 3
    while divisor * divisor <= value:
        if value % divisor == 0:
            return False
        divisor += 2
    return True


def _next_prime(value: int) -> int:
    candidate = max(2, int(value))
    while not _is_prime(candidate):
        candidate += 1
    return candidate


@dataclass(frozen=True)
class CRTBlock:
    packed: int
    moduli: tuple[int, ...]
    length: int

    @property
    def wire_bytes(self) -> int:
        return max(1, (self.packed.bit_length() + 7) // 8) + sum(
            max(1, (modulus.bit_length() + 7) // 8) for modulus in self.moduli
        )


class CRTVectorCodec:
    """Lossless signed-integer CRT packing for the PrivLDFL proxy.

    One pairwise-coprime modulus is assigned per coordinate in a block.  This
    makes packing/unpacking auditable and detects bound violations.  It models
    the paper-level CRT compression idea without claiming the unavailable
    authors' exact modulus schedule or wire format.
    """

    def __init__(self, bound: int, block_size: int = 32) -> None:
        if bound < 0:
            raise ValueError("bound must be non-negative")
        if block_size <= 0:
            raise ValueError("block_size must be positive")
        self.bound = int(bound)
        self.block_size = int(block_size)
        moduli = []
        candidate = 2 * self.bound + 2
        for _ in range(self.block_size):
            prime = _next_prime(candidate)
            moduli.append(prime)
            candidate = prime + 1
        self.moduli = tuple(moduli)

    @staticmethod
    def _pack_block(values: Sequence[int], moduli: Sequence[int]) -> int:
        product = math.prod(moduli)
        packed = 0
        for value, modulus in zip(values, moduli):
            partial = product // modulus
            packed = (packed + (int(value) % modulus) * partial * pow(partial, -1, modulus)) % product
        return packed

    def pack(self, values: Sequence[int]) -> list[CRTBlock]:
        result = []
        for offset in range(0, len(values), self.block_size):
            chunk = [int(value) for value in values[offset : offset + self.block_size]]
            if any(abs(value) > self.bound for value in chunk):
                raise ValueError("CRT input exceeds configured signed bound")
            moduli = self.moduli[: len(chunk)]
            result.append(CRTBlock(self._pack_block(chunk, moduli), moduli, len(chunk)))
        return result

    def unpack(self, blocks: Sequence[CRTBlock]) -> list[int]:
        values: list[int] = []
        for block in blocks:
            if block.length != len(block.moduli):
                raise ValueError("invalid CRT block metadata")
            for modulus in block.moduli:
                residue = block.packed % modulus
                signed = residue if residue <= modulus // 2 else residue - modulus
                if abs(signed) > self.bound:
                    raise ValueError("decoded CRT value exceeds configured signed bound")
                values.append(signed)
        return values


@dataclass(frozen=True)
class PrivLDFLAggregationResult:
    global_state: OrderedDict[str, torch.Tensor]
    exact_roundtrip: bool
    client_wire_bytes: int
    implementation_status: str = "clean-room-crt-reconstruction"


class PrivLDFLReconstruction:
    """Accuracy-compatible PrivLDFL proxy with measurable CRT communication."""

    def __init__(
        self,
        template_state: OrderedDict[str, torch.Tensor] | dict[str, torch.Tensor],
        codec: FixedPointCodec,
        block_size: int = 32,
    ) -> None:
        _, self.spec = flatten_state_dict(template_state)
        self.codec = codec
        self.crt = CRTVectorCodec(codec.encoded_bound, block_size)

    def aggregate(
        self,
        states: Sequence[OrderedDict[str, torch.Tensor] | dict[str, torch.Tensor]],
        sample_counts: Sequence[int],
    ) -> PrivLDFLAggregationResult:
        if not states or len(states) != len(sample_counts):
            raise ValueError("one positive sample count is required per client state")
        counts = [int(value) for value in sample_counts]
        if any(value <= 0 for value in counts):
            raise ValueError("sample counts must be positive")
        encoded: list[list[int]] = []
        wire_bytes = 0
        for state in states:
            vector, spec = flatten_state_dict(state)
            if spec != self.spec:
                raise ValueError("client model structure differs from template")
            original = self.codec.encode(vector.tolist())
            blocks = self.crt.pack(original)
            recovered = self.crt.unpack(blocks)
            if recovered != original:
                raise ValueError("CRT roundtrip changed a client update")
            encoded.append(recovered)
            wire_bytes += sum(block.wire_bytes for block in blocks)

        divisor = reduce(math.gcd, counts)
        weights = [value // divisor for value in counts]
        denominator = sum(weights)
        average = torch.tensor(
            [
                sum(encoded[i][z] * weights[i] for i in range(len(encoded)))
                / self.codec.scale
                / denominator
                for z in range(self.spec.total_numel)
            ],
            dtype=torch.float64,
        )
        return PrivLDFLAggregationResult(
            global_state=unflatten_state_dict(average, self.spec),
            exact_roundtrip=True,
            client_wire_bytes=wire_bytes,
        )
