from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HybridAlphaProfile:
    """Configuration for the single-aggregator comparison path.

    The supplied manuscript describes HybridAlpha as a comparison point but
    does not provide runnable source or all protocol parameters.  We therefore
    use the tMCFE implementation's one-of-one specialization while preserving
    the same model, optimizer, codec, and client split as CrosFed.
    """

    aggregators: int = 1
    threshold: int = 1
    committee: tuple[int, ...] = (1,)
    implementation_status: str = "derived-single-aggregator-reconstruction"


def hybridalpha_profile() -> HybridAlphaProfile:
    return HybridAlphaProfile()
