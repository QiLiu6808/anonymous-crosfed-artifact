from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class HMACSignatureProvider:
    """Simulation-only authentication provider with per-identity secrets.

    Production ChainMaker deployments replace this provider with the chain account
    signature implementation. HMAC is intentionally named so it cannot be confused
    with the manuscript's public-key deployment.
    """

    secrets_by_identity: Mapping[str, bytes]

    @classmethod
    def generate(cls, identities: list[str]) -> "HMACSignatureProvider":
        return cls({identity: secrets.token_bytes(32) for identity in identities})

    def sign(self, signer_id: str, message: bytes) -> str:
        secret = self.secrets_by_identity.get(signer_id)
        if secret is None:
            raise KeyError(f"unregistered signer: {signer_id}")
        return hmac.new(secret, message, hashlib.sha256).hexdigest()

    def verify(self, signer_id: str, message: bytes, signature: str) -> bool:
        secret = self.secrets_by_identity.get(signer_id)
        if secret is None:
            return False
        expected = hmac.new(secret, message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

