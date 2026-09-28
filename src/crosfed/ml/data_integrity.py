from __future__ import annotations

import hashlib
import struct
from collections import Counter
from typing import Any

import numpy as np
import torch
from torch.utils.data import Dataset, Subset


def _base_dataset_and_indices(dataset: Dataset) -> tuple[Dataset, list[int]]:
    indices = list(range(len(dataset)))
    current = dataset
    while isinstance(current, Subset):
        parent_indices = [int(value) for value in current.indices]
        indices = [parent_indices[index] for index in indices]
        current = current.dataset
    return current, indices


def _as_numpy(value: Any) -> np.ndarray:
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().numpy()
    return np.asarray(value)


def dataset_content_manifest(dataset: Dataset) -> dict[str, Any]:
    """Hash raw examples and labels before transforms are applied.

    torchvision MNIST and CIFAR datasets expose raw ``data`` and ``targets``.
    Failing explicitly for another dataset avoids silently hashing randomized
    augmentations or Python object representations.
    """

    base, indices = _base_dataset_and_indices(dataset)
    if not hasattr(base, "data") or not hasattr(base, "targets"):
        raise TypeError("dataset must expose raw data and targets for content hashing")
    raw_data = getattr(base, "data")
    raw_targets = getattr(base, "targets")
    digest = hashlib.sha256()
    histogram: Counter[int] = Counter()
    first_shape: tuple[int, ...] | None = None
    first_dtype: str | None = None
    for index in indices:
        sample = np.ascontiguousarray(_as_numpy(raw_data[index]))
        target_array = _as_numpy(raw_targets[index]).reshape(-1)
        if target_array.size != 1:
            raise ValueError("classification target must contain exactly one value")
        target = int(target_array[0])
        histogram[target] += 1
        if first_shape is None:
            first_shape = tuple(int(value) for value in sample.shape)
            first_dtype = str(sample.dtype)
        digest.update(struct.pack(">Q", int(index)))
        digest.update(str(sample.dtype).encode("ascii"))
        digest.update(struct.pack(">I", sample.ndim))
        for dimension in sample.shape:
            digest.update(struct.pack(">Q", int(dimension)))
        digest.update(memoryview(sample).cast("B"))
        digest.update(struct.pack(">q", target))
    return {
        "dataset_class": type(base).__name__,
        "samples": len(indices),
        "content_sha256": digest.hexdigest(),
        "sample_shape": list(first_shape or ()),
        "sample_dtype": first_dtype,
        "class_histogram": {
            str(label): count for label, count in sorted(histogram.items())
        },
    }
