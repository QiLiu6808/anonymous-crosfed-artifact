from __future__ import annotations

from collections import OrderedDict

import pytest
import torch

from crosfed.baselines import CRTVectorCodec, PrivLDFLReconstruction, hybridalpha_profile
from crosfed.crypto import FixedPointCodec


def test_crt_codec_roundtrips_signed_blocks_and_rejects_overflow() -> None:
    codec = CRTVectorCodec(bound=10, block_size=3)
    values = [-10, -1, 0, 1, 10, 4, -3]
    assert codec.unpack(codec.pack(values)) == values
    with pytest.raises(ValueError, match="exceeds"):
        codec.pack([11])


def test_privldfl_proxy_matches_quantized_weighted_average() -> None:
    template = OrderedDict(weight=torch.tensor([0.0, 0.0]))
    states = [
        OrderedDict(weight=torch.tensor([1.0, -2.0])),
        OrderedDict(weight=torch.tensor([3.0, 2.0])),
    ]
    baseline = PrivLDFLReconstruction(template, FixedPointCodec(scale=100, clip=8), block_size=2)
    result = baseline.aggregate(states, [1, 3])
    assert result.exact_roundtrip
    assert torch.allclose(result.global_state["weight"], torch.tensor([2.5, 1.0]))
    assert result.client_wire_bytes > 0


def test_hybridalpha_profile_is_one_of_one() -> None:
    profile = hybridalpha_profile()
    assert (profile.aggregators, profile.threshold, profile.committee) == (1, 1, (1,))
