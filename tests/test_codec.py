import pytest

from crosfed.crypto import FixedPointCodec


def test_fixed_point_round_trip_and_clipping() -> None:
    codec = FixedPointCodec(scale=100, clip=2.0)
    encoded = codec.encode([-3.0, -1.25, 0.0, 1.234, 9.0])
    assert encoded == [-200, -125, 0, 123, 200]
    assert codec.decode(encoded) == pytest.approx([-2.0, -1.25, 0.0, 1.23, 2.0])

