from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from math import prod

import torch


@dataclass(frozen=True)
class TensorSpec:
    name: str
    shape: tuple[int, ...]
    dtype: torch.dtype
    numel: int


@dataclass(frozen=True)
class ModelVectorSpec:
    tensors: tuple[TensorSpec, ...]
    total_numel: int


def flatten_state_dict(
    state: OrderedDict[str, torch.Tensor] | dict[str, torch.Tensor],
) -> tuple[torch.Tensor, ModelVectorSpec]:
    """Flatten a state dict in its declared order using float64 as the wire oracle."""

    specs: list[TensorSpec] = []
    chunks: list[torch.Tensor] = []
    for name, tensor in state.items():
        detached = tensor.detach().cpu()
        shape = tuple(detached.shape)
        numel = detached.numel()
        specs.append(TensorSpec(name, shape, detached.dtype, numel))
        chunks.append(detached.reshape(-1).to(torch.float64))
    vector = torch.cat(chunks) if chunks else torch.empty(0, dtype=torch.float64)
    return vector, ModelVectorSpec(tuple(specs), vector.numel())


def unflatten_state_dict(
    vector: torch.Tensor, spec: ModelVectorSpec
) -> OrderedDict[str, torch.Tensor]:
    """Restore the exact names, shapes and dtypes captured by ``flatten_state_dict``."""

    flat = vector.detach().cpu().reshape(-1)
    if flat.numel() != spec.total_numel:
        raise ValueError(
            f"model vector has {flat.numel()} values, expected {spec.total_numel}"
        )
    restored: OrderedDict[str, torch.Tensor] = OrderedDict()
    offset = 0
    for tensor_spec in spec.tensors:
        if prod(tensor_spec.shape) != tensor_spec.numel:
            raise ValueError(f"invalid tensor spec for {tensor_spec.name}")
        chunk = flat[offset : offset + tensor_spec.numel]
        restored[tensor_spec.name] = chunk.reshape(tensor_spec.shape).to(tensor_spec.dtype)
        offset += tensor_spec.numel
    return restored

