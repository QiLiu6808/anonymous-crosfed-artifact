import torch

from crosfed.ml import PaperMNISTCNNCandidate, flatten_state_dict, unflatten_state_dict


def test_model_state_flatten_round_trip_is_exact() -> None:
    model = PaperMNISTCNNCandidate("b")
    original = model.state_dict()
    vector, spec = flatten_state_dict(original)
    restored = unflatten_state_dict(vector, spec)
    assert vector.numel() == 19_518
    assert list(restored) == list(original)
    for name in original:
        assert restored[name].dtype == original[name].dtype
        assert restored[name].shape == original[name].shape
        assert torch.equal(restored[name], original[name])


def test_unflatten_rejects_wrong_vector_length() -> None:
    model = PaperMNISTCNNCandidate("b")
    vector, spec = flatten_state_dict(model.state_dict())
    try:
        unflatten_state_dict(vector[:-1], spec)
    except ValueError as exc:
        assert "expected 19518" in str(exc)
    else:
        raise AssertionError("wrong-length model vector was accepted")

