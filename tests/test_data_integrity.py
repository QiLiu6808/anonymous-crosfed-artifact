from __future__ import annotations

import numpy as np
from torch.utils.data import Dataset, Subset

from crosfed.ml import dataset_content_manifest


class RawDataset(Dataset):
    def __init__(self) -> None:
        self.data = np.arange(24, dtype=np.uint8).reshape(3, 2, 4)
        self.targets = [0, 1, 1]

    def __len__(self) -> int:
        return len(self.targets)

    def __getitem__(self, index: int):
        return self.data[index], self.targets[index]


def test_dataset_manifest_is_deterministic_and_subset_aware() -> None:
    dataset = RawDataset()
    first = dataset_content_manifest(Subset(dataset, [2, 0]))
    second = dataset_content_manifest(Subset(dataset, [2, 0]))
    reordered = dataset_content_manifest(Subset(dataset, [0, 2]))
    assert first == second
    assert first["samples"] == 2
    assert first["class_histogram"] == {"0": 1, "1": 1}
    assert first["content_sha256"] != reordered["content_sha256"]


def test_dataset_manifest_detects_content_change() -> None:
    dataset = RawDataset()
    before = dataset_content_manifest(dataset)["content_sha256"]
    dataset.data[0, 0, 0] += 1
    assert dataset_content_manifest(dataset)["content_sha256"] != before
