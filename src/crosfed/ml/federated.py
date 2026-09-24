from __future__ import annotations

import copy
import random
from collections import OrderedDict
from typing import Sequence

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset, Subset


class TinyMNISTCNN(nn.Module):
    """Fast sanity model; the paper-parameterized 19,518 model is an M1 gate."""

    def __init__(self) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 8, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(8, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        )
        self.classifier = nn.Linear(16 * 7 * 7, 10)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(inputs).flatten(1))


class PaperMNISTCNNCandidate(nn.Module):
    """Parameter-count exact candidates for the underspecified 19,518-param CNN.

    The manuscript gives only the family and total parameter count. These candidates
    use two padded 3x3 convolutions, two 2x2 pools, and one hidden linear layer. Each
    registered width tuple reaches the target naturally, without unused parameters.
    """

    CANDIDATES = {
        "a": (10, 40, 8),
        "b": (13, 16, 22),
        "c": (19, 27, 11),
    }
    TARGET_PARAMETERS = 19_518

    def __init__(self, candidate: str = "b") -> None:
        super().__init__()
        if candidate not in self.CANDIDATES:
            raise ValueError(f"unknown paper CNN candidate: {candidate}")
        channels1, channels2, hidden = self.CANDIDATES[candidate]
        self.candidate = candidate
        self.features = nn.Sequential(
            nn.Conv2d(1, channels1, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(channels1, channels2, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Linear(channels2 * 7 * 7, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 10),
        )
        parameter_count = sum(parameter.numel() for parameter in self.parameters())
        if parameter_count != self.TARGET_PARAMETERS:
            raise RuntimeError(
                f"candidate {candidate} has {parameter_count} parameters, "
                f"expected {self.TARGET_PARAMETERS}"
            )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(inputs).flatten(1))


class PaperCIFAR10MicroNetCandidate(nn.Module):
    """Auditable 73,198-parameter CIFAR-10 candidate.

    The supplied manuscript identifies MicroNet and the total parameter count but
    omits its adaptation. This compact three-stage candidate uses only active
    convolution/linear parameters and is therefore suitable for calibration without
    pretending to be the unreleased author configuration.
    """

    TARGET_PARAMETERS = 73_198

    def __init__(self) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 18, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(18, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 58, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Linear(58 * 4 * 4, 54),
            nn.ReLU(),
            nn.Linear(54, 10),
        )
        parameter_count = sum(parameter.numel() for parameter in self.parameters())
        if parameter_count != self.TARGET_PARAMETERS:
            raise RuntimeError(
                f"CIFAR candidate has {parameter_count} parameters, "
                f"expected {self.TARGET_PARAMETERS}"
            )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(inputs).flatten(1))


def build_mnist_model(model_name: str, candidate: str = "b") -> nn.Module:
    if model_name == "tiny":
        return TinyMNISTCNN()
    if model_name == "paper_candidate":
        return PaperMNISTCNNCandidate(candidate)
    raise ValueError(f"unknown MNIST model: {model_name}")


def build_image_model(dataset: str, model_name: str, candidate: str = "b") -> nn.Module:
    if dataset == "mnist":
        return build_mnist_model(model_name, candidate)
    if dataset == "cifar10" and model_name == "paper_candidate":
        return PaperCIFAR10MicroNetCandidate()
    raise ValueError(f"unknown model {model_name!r} for dataset {dataset!r}")


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def partition_iid(dataset: Dataset, clients: int, seed: int) -> list[Subset]:
    generator = torch.Generator().manual_seed(seed)
    indices = torch.randperm(len(dataset), generator=generator).tolist()
    return [Subset(dataset, indices[i::clients]) for i in range(clients)]


def train_local(
    global_model: nn.Module,
    dataset: Dataset,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    device: torch.device,
    optimizer_name: str = "sgd",
    momentum: float = 0.9,
    weight_decay: float = 0.0,
) -> tuple[OrderedDict[str, torch.Tensor], float]:
    model = copy.deepcopy(global_model).to(device)
    model.train()
    if optimizer_name == "sgd":
        optimizer = torch.optim.SGD(
            model.parameters(), lr=learning_rate, momentum=momentum, weight_decay=weight_decay
        )
    elif optimizer_name == "adam":
        optimizer = torch.optim.Adam(
            model.parameters(), lr=learning_rate, weight_decay=weight_decay
        )
    else:
        raise ValueError(f"unsupported optimizer: {optimizer_name}")
    criterion = nn.CrossEntropyLoss()
    total_loss = 0.0
    seen = 0
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0)
    for _ in range(epochs):
        for inputs, targets in loader:
            inputs, targets = inputs.to(device), targets.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(inputs), targets)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item()) * targets.size(0)
            seen += targets.size(0)
    state = OrderedDict((key, value.detach().cpu().clone()) for key, value in model.state_dict().items())
    return state, total_loss / max(seen, 1)


def fedavg(states: Sequence[OrderedDict[str, torch.Tensor]], weights: Sequence[int]) -> OrderedDict[str, torch.Tensor]:
    if not states or len(states) != len(weights) or sum(weights) <= 0:
        raise ValueError("states and positive weights are required")
    total = float(sum(weights))
    result: OrderedDict[str, torch.Tensor] = OrderedDict()
    for key in states[0]:
        accumulator = torch.zeros_like(states[0][key], dtype=torch.float64)
        for state, weight in zip(states, weights):
            accumulator += state[key].to(torch.float64) * (weight / total)
        result[key] = accumulator.to(states[0][key].dtype)
    return result


@torch.no_grad()
def evaluate(model: nn.Module, dataset: Dataset, batch_size: int, device: torch.device) -> dict[str, float]:
    model = model.to(device).eval()
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)
    criterion = nn.CrossEntropyLoss(reduction="sum")
    total_loss = 0.0
    correct = 0
    total = 0
    for inputs, targets in loader:
        inputs, targets = inputs.to(device), targets.to(device)
        logits = model(inputs)
        total_loss += float(criterion(logits, targets).item())
        correct += int((logits.argmax(1) == targets).sum().item())
        total += targets.size(0)
    return {"loss": total_loss / total, "accuracy": correct / total, "samples": total}
