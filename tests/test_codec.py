import pytest

from crosfed.crypto import FixedPointCodec


def test_fixed_point_round_trip_and_clipping() -> None:
    codec = FixedPointCodec(scale=100, clip=2.0)
    encoded = codec.encode([-3.0, -1.25, 0.0, 1.234, 9.0])
    assert encoded == [-200, -125, 0, 123, 200]
    assert codec.decode(encoded) == pytest.approx([-2.0, -1.25, 0.0, 1.23, 2.0])


def test_fixed_point_diagnostics_report_clipping_and_bound_use() -> None:
    codec = FixedPointCodec(scale=100, clip=2.0)
    encoded, diagnostics = codec.encode_with_diagnostics([-3.0, -2.0, 0.0, 1.5])
    assert encoded == [-200, -200, 0, 150]
    assert diagnostics.count == 4
    assert diagnostics.max_abs == 3.0
    assert diagnostics.clipped_count == 1
    assert diagnostics.saturated_count == 2
    assert diagnostics.clipped_fraction == 0.25
    assert diagnostics.bound_utilization == 1.0
