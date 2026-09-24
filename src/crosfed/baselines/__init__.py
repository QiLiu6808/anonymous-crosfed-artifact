"""Reconstructed comparison baselines used by the experiment runner.

These modules are clean-room protocol adapters, not source releases from the
original baseline authors.  Every result records that distinction explicitly.
"""

from .hybridalpha import HybridAlphaProfile, hybridalpha_profile
from .privldfl import (
    CRTBlock,
    CRTVectorCodec,
    PrivLDFLAggregationResult,
    PrivLDFLReconstruction,
)

__all__ = [
    "CRTBlock",
    "CRTVectorCodec",
    "HybridAlphaProfile",
    "PrivLDFLAggregationResult",
    "PrivLDFLReconstruction",
    "hybridalpha_profile",
]
