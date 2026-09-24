import pytest
import torch

from crosfed.ml import PaperCIFAR10MicroNetCandidate, PaperMNISTCNNCandidate


@pytest.mark.parametrize("candidate", ["a", "b", "c"])
def test_paper_mnist_candidates_have_exact_parameter_count(candidate: str) -> None:
    model = PaperMNISTCNNCandidate(candidate)
    assert sum(parameter.numel() for parameter in model.parameters()) == 19_518


def test_cifar_candidate_has_exact_parameter_count_and_shape() -> None:
    model = PaperCIFAR10MicroNetCandidate()
    assert sum(parameter.numel() for parameter in model.parameters()) == 73_198
    assert tuple(model(torch.zeros(2, 3, 32, 32)).shape) == (2, 10)
