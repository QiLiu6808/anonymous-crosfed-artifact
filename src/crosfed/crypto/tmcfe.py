from __future__ import annotations

import base64
import hashlib
import math
from dataclasses import dataclass, replace
from typing import Any, Iterable, Sequence

try:
    from charm.toolbox.pairinggroup import G1, ZR, PairingGroup
except ImportError as exc:  # pragma: no cover - exercised on the remote crypto env
    G1 = ZR = PairingGroup = None
    _CHARM_IMPORT_ERROR = exc
else:
    _CHARM_IMPORT_ERROR = None


class TMCFEError(ValueError):
    """Raised when a protocol invariant is violated."""


@dataclass(frozen=True)
class PublicParameters:
    group_name: str
    group: Any
    generator: Any
    order: int
    clients: int
    dimension: int


@dataclass(frozen=True)
class MasterSecret:
    alpha: tuple[int, ...]
    w: tuple[tuple[int, ...], ...]
    u: tuple[tuple[int, ...], ...]
    g_alpha: tuple[Any, ...]
    g_alpha_w: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True)
class EncryptionKey:
    client_id: int
    g_alpha: tuple[Any, ...]
    g_alpha_w: tuple[Any, ...]
    u: tuple[int, ...]


@dataclass(frozen=True)
class FunctionalShareKey:
    aggregator_id: int
    round_id: int
    threshold: int
    function_digest: str
    v0: tuple[int, ...]
    v1: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class Ciphertext:
    client_id: int
    round_id: int
    ct0: tuple[Any, ...]
    ct1: tuple[Any, ...]


@dataclass(frozen=True)
class PartialShare:
    aggregator_id: int
    round_id: int
    threshold: int
    committee: tuple[int, ...]
    function_digest: str
    numerator: tuple[Any, ...]
    denominator_client: tuple[tuple[Any, ...], ...]
    denominator_round: tuple[Any, ...]


def _function_digest(weights: Sequence[Sequence[int]]) -> str:
    canonical = ";".join(",".join(str(int(x)) for x in row) for row in weights)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def function_digest(weights: Sequence[Sequence[int]]) -> str:
    return _function_digest(weights)


class ThresholdMCFE:
    """Paper-faithful vector tMCFE reference implementation over Charm SS512."""

    def __init__(self, group_name: str = "SS512") -> None:
        if PairingGroup is None:
            raise RuntimeError(
                "Charm pairing backend is unavailable; ensure libpbc.so.1 is on LD_LIBRARY_PATH"
            ) from _CHARM_IMPORT_ERROR
        self.group_name = group_name
        self.pp: PublicParameters | None = None
        self.msk: MasterSecret | None = None
        self._dlog_cache: dict[bytes, int] | None = None
        self._dlog_cache_bound = -1

    def _zr(self, value: int) -> Any:
        assert self.pp is not None
        return self.pp.group.init(ZR, int(value) % self.pp.order)

    def _random_int(self) -> int:
        assert self.pp is not None
        return int(self.pp.group.random(ZR))

    def _hash_round(self, round_id: int) -> int:
        assert self.pp is not None
        return int(self.pp.group.hash(f"crosfed-round:{round_id}".encode("ascii"), ZR))

    def setup(self, clients: int, dimension: int) -> PublicParameters:
        if clients <= 0 or dimension <= 0:
            raise TMCFEError("clients and dimension must be positive")
        group = PairingGroup(self.group_name)
        generator = group.random(G1)
        self.pp = PublicParameters(
            self.group_name, group, generator, int(group.order()), clients, dimension
        )
        alpha = tuple(self._random_int() for _ in range(dimension))
        w = tuple(
            tuple(self._random_int() for _ in range(dimension)) for _ in range(clients)
        )
        u = tuple(
            tuple(self._random_int() for _ in range(dimension)) for _ in range(clients)
        )
        g_alpha = tuple(generator ** self._zr(a) for a in alpha)
        g_alpha_w = tuple(
            tuple(generator ** self._zr(alpha[z] * w[i][z]) for z in range(dimension))
            for i in range(clients)
        )
        self.msk = MasterSecret(alpha, w, u, g_alpha, g_alpha_w)
        self._dlog_cache = None
        self._dlog_cache_bound = -1
        return self.pp

    def encryption_key(self, client_id: int) -> EncryptionKey:
        pp, msk = self._require_setup()
        self._validate_id(client_id, pp.clients, "client")
        row = client_id - 1
        return EncryptionKey(client_id, msk.g_alpha, msk.g_alpha_w[row], msk.u[row])

    def generate_functional_keys(
        self,
        weights: Sequence[Sequence[int]],
        aggregator_ids: Sequence[int],
        threshold: int,
        round_id: int,
    ) -> dict[int, FunctionalShareKey]:
        pp, msk = self._require_setup()
        self._validate_weights(weights)
        ids = tuple(int(x) for x in aggregator_ids)
        if len(set(ids)) != len(ids) or any(x <= 0 for x in ids):
            raise TMCFEError("aggregator IDs must be unique positive integers")
        if not 1 <= threshold <= len(ids):
            raise TMCFEError("threshold must be between one and aggregator count")

        h = self._hash_round(round_id)
        a0 = [
            h * sum(int(weights[i][z]) * msk.u[i][z] for i in range(pp.clients))
            for z in range(pp.dimension)
        ]
        b0 = [
            [int(weights[i][z]) * msk.w[i][z] for z in range(pp.dimension)]
            for i in range(pp.clients)
        ]
        a_coeff = [a0] + [
            [self._random_int() for _ in range(pp.dimension)] for _ in range(threshold - 1)
        ]
        b_coeff = [[b0[i]] + [
            [self._random_int() for _ in range(pp.dimension)] for _ in range(threshold - 1)
        ] for i in range(pp.clients)]
        digest = _function_digest(weights)

        result: dict[int, FunctionalShareKey] = {}
        for aggregator_id in ids:
            v0 = tuple(
                sum(a_coeff[k][z] * pow(aggregator_id, k, pp.order) for k in range(threshold))
                % pp.order
                for z in range(pp.dimension)
            )
            v1 = tuple(
                tuple(
                    sum(
                        b_coeff[i][k][z] * pow(aggregator_id, k, pp.order)
                        for k in range(threshold)
                    ) % pp.order
                    for z in range(pp.dimension)
                )
                for i in range(pp.clients)
            )
            result[aggregator_id] = FunctionalShareKey(
                aggregator_id, round_id, threshold, digest, v0, v1
            )
        return result

    def encrypt(
        self, values: Sequence[int], key: EncryptionKey, round_id: int
    ) -> Ciphertext:
        pp, _ = self._require_setup()
        if len(values) != pp.dimension:
            raise TMCFEError("plaintext dimension mismatch")
        h = self._hash_round(round_id)
        ct0: list[Any] = []
        ct1: list[Any] = []
        for z, value in enumerate(values):
            randomness = self._random_int()
            masked = pp.generator ** self._zr(int(value) + h * key.u[z])
            ct0.append(masked * (key.g_alpha_w[z] ** self._zr(randomness)))
            ct1.append(key.g_alpha[z] ** self._zr(randomness))
        return Ciphertext(key.client_id, round_id, tuple(ct0), tuple(ct1))

    def share_decrypt(
        self,
        ciphertexts: Sequence[Ciphertext],
        weights: Sequence[Sequence[int]],
        key: FunctionalShareKey,
        committee: Sequence[int],
        round_id: int,
    ) -> PartialShare:
        pp, _ = self._require_setup()
        self._validate_weights(weights)
        ordered = sorted(ciphertexts, key=lambda item: item.client_id)
        if [item.client_id for item in ordered] != list(range(1, pp.clients + 1)):
            raise TMCFEError("exactly one ciphertext from every client is required")
        if any(item.round_id != round_id for item in ordered) or key.round_id != round_id:
            raise TMCFEError("round mismatch or replay detected")
        digest = _function_digest(weights)
        if key.function_digest != digest:
            raise TMCFEError("function/weight mismatch")
        committee_tuple = tuple(sorted(int(x) for x in committee))
        if len(set(committee_tuple)) != len(committee_tuple):
            raise TMCFEError("committee contains duplicate aggregators")
        if key.aggregator_id not in committee_tuple or len(committee_tuple) < key.threshold:
            raise TMCFEError("invalid threshold committee")
        lagrange = self._lagrange_at_zero(key.aggregator_id, committee_tuple)

        numerator = []
        for z in range(pp.dimension):
            acc = pp.generator ** self._zr(0)
            for i, ciphertext in enumerate(ordered):
                acc *= ciphertext.ct0[z] ** self._zr(weights[i][z])
            numerator.append(acc)
        denominator_client = tuple(
            tuple(
                ordered[i].ct1[z] ** self._zr(key.v1[i][z] * lagrange)
                for z in range(pp.dimension)
            )
            for i in range(pp.clients)
        )
        denominator_round = tuple(
            pp.generator ** self._zr(key.v0[z] * lagrange) for z in range(pp.dimension)
        )
        return PartialShare(
            key.aggregator_id,
            round_id,
            key.threshold,
            committee_tuple,
            digest,
            tuple(numerator),
            denominator_client,
            denominator_round,
        )

    def combine(
        self, shares: Sequence[PartialShare], round_id: int, dlog_bound: int
    ) -> list[int]:
        pp, _ = self._require_setup()
        if not shares:
            raise TMCFEError("no partial shares")
        first = shares[0]
        committee = first.committee
        signer_ids = [share.aggregator_id for share in shares]
        if len(set(signer_ids)) != len(signer_ids):
            raise TMCFEError("duplicate aggregator share")
        if len(shares) < first.threshold:
            raise TMCFEError("insufficient partial shares")
        if set(signer_ids) != set(committee):
            raise TMCFEError("all shares from the frozen committee are required")
        if any(
            share.round_id != round_id
            or share.committee != committee
            or share.threshold != first.threshold
            or share.function_digest != first.function_digest
            for share in shares
        ):
            raise TMCFEError("partial share context mismatch")
        reference = tuple(pp.group.serialize(value) for value in first.numerator)
        if any(
            tuple(pp.group.serialize(value) for value in share.numerator) != reference
            for share in shares[1:]
        ):
            raise TMCFEError("inconsistent shared numerator")

        table = self._dlog_table(dlog_bound)
        decoded: list[int] = []
        identity = pp.generator ** self._zr(0)
        for z in range(pp.dimension):
            denominator = pp.generator ** self._zr(0)
            for share in shares:
                for client_terms in share.denominator_client:
                    denominator *= client_terms[z]
                denominator *= share.denominator_round[z]
            element = first.numerator[z] / denominator
            exponent = 0 if element == identity else table.get(pp.group.serialize(element))
            if exponent is None:
                # Charm SS512 can serialize an arithmetically produced element
                # differently from the same directly exponentiated element
                # (most visibly for the identity). Equality above handles zero;
                # bounded BSGS is a correctness fallback for any other
                # non-canonical representation. The plaintext oracle below the
                # protocol layer still enforces exact coordinate equality.
                diagnostic = self._bounded_dlog_bsgs(element, dlog_bound)
                if diagnostic is not None:
                    decoded.append(diagnostic)
                    continue
                diagnostic_bound = max(1_000_000, dlog_bound * 8)
                diagnostic = self._bounded_dlog_bsgs(element, diagnostic_bound)
                detail = (
                    f"; diagnostic exponent={diagnostic}"
                    if diagnostic is not None
                    else f"; not found within ±{diagnostic_bound}"
                )
                raise TMCFEError(
                    f"discrete log outside signed bound ±{dlog_bound} at coordinate {z}{detail}"
                )
            decoded.append(exponent)
        return decoded

    def _bounded_dlog_bsgs(self, element: Any, bound: int) -> int | None:
        """Diagnostic signed baby-step/giant-step lookup for one failed coordinate."""

        pp, _ = self._require_setup()
        width = 2 * int(bound) + 1
        step = math.isqrt(width) + 1
        baby: dict[bytes, int] = {}
        current = pp.generator ** self._zr(0)
        for offset in range(step):
            baby.setdefault(pp.group.serialize(current), offset)
            current *= pp.generator
        shifted = element * (pp.generator ** self._zr(bound))
        factor = pp.generator ** self._zr(-step)
        for giant in range(step + 1):
            offset = baby.get(pp.group.serialize(shifted))
            if offset is not None:
                unsigned = giant * step + offset
                if unsigned < width:
                    return unsigned - bound
            shifted *= factor
        return None

    def serialized_size(self, value: Ciphertext | PartialShare) -> int:
        pp, _ = self._require_setup()
        if isinstance(value, Ciphertext):
            elements: Iterable[Any] = (*value.ct0, *value.ct1)
        else:
            elements = (
                *value.numerator,
                *(item for row in value.denominator_client for item in row),
                *value.denominator_round,
            )
        return sum(len(pp.group.serialize(element)) for element in elements)

    def ciphertext_to_payload(self, value: Ciphertext) -> dict[str, Any]:
        return {
            "client_id": value.client_id,
            "round_id": value.round_id,
            "ct0": [self._encode_group(item) for item in value.ct0],
            "ct1": [self._encode_group(item) for item in value.ct1],
        }

    def ciphertext_from_payload(self, value: dict[str, Any]) -> Ciphertext:
        return Ciphertext(
            int(value["client_id"]),
            int(value["round_id"]),
            tuple(self._decode_group(item) for item in value["ct0"]),
            tuple(self._decode_group(item) for item in value["ct1"]),
        )

    def partial_share_to_payload(self, value: PartialShare) -> dict[str, Any]:
        return {
            "aggregator_id": value.aggregator_id,
            "round_id": value.round_id,
            "threshold": value.threshold,
            "committee": list(value.committee),
            "function_digest": value.function_digest,
            "numerator": [self._encode_group(item) for item in value.numerator],
            "denominator_client": [
                [self._encode_group(item) for item in row]
                for row in value.denominator_client
            ],
            "denominator_round": [
                self._encode_group(item) for item in value.denominator_round
            ],
        }

    def partial_share_from_payload(self, value: dict[str, Any]) -> PartialShare:
        return PartialShare(
            aggregator_id=int(value["aggregator_id"]),
            round_id=int(value["round_id"]),
            threshold=int(value["threshold"]),
            committee=tuple(int(item) for item in value["committee"]),
            function_digest=str(value["function_digest"]),
            numerator=tuple(self._decode_group(item) for item in value["numerator"]),
            denominator_client=tuple(
                tuple(self._decode_group(item) for item in row)
                for row in value["denominator_client"]
            ),
            denominator_round=tuple(
                self._decode_group(item) for item in value["denominator_round"]
            ),
        )

    def tamper_numerator(self, share: PartialShare, coordinate: int = 0) -> PartialShare:
        pp, _ = self._require_setup()
        changed = list(share.numerator)
        changed[coordinate] *= pp.generator
        return replace(share, numerator=tuple(changed))

    def _dlog_table(self, bound: int) -> dict[bytes, int]:
        pp, _ = self._require_setup()
        if bound < 0:
            raise TMCFEError("dlog bound must be non-negative")
        if self._dlog_cache is not None and bound <= self._dlog_cache_bound:
            return self._dlog_cache
        self._dlog_cache = {
            pp.group.serialize(pp.generator ** self._zr(exponent)): exponent
            for exponent in range(-bound, bound + 1)
        }
        self._dlog_cache_bound = bound
        return self._dlog_cache

    def _encode_group(self, value: Any) -> str:
        pp, _ = self._require_setup()
        return base64.b64encode(pp.group.serialize(value)).decode("ascii")

    def _decode_group(self, value: str) -> Any:
        pp, _ = self._require_setup()
        return pp.group.deserialize(base64.b64decode(value.encode("ascii")))

    def _lagrange_at_zero(self, identity: int, committee: Sequence[int]) -> int:
        pp, _ = self._require_setup()
        numerator = 1
        denominator = 1
        for other in committee:
            if other == identity:
                continue
            numerator = numerator * (-other) % pp.order
            denominator = denominator * (identity - other) % pp.order
        return numerator * pow(denominator, -1, pp.order) % pp.order

    def _validate_weights(self, weights: Sequence[Sequence[int]]) -> None:
        pp, _ = self._require_setup()
        if len(weights) != pp.clients or any(len(row) != pp.dimension for row in weights):
            raise TMCFEError("weight matrix shape mismatch")

    @staticmethod
    def _validate_id(identity: int, maximum: int, kind: str) -> None:
        if not 1 <= identity <= maximum:
            raise TMCFEError(f"{kind} ID out of range")

    def _require_setup(self) -> tuple[PublicParameters, MasterSecret]:
        if self.pp is None or self.msk is None:
            raise TMCFEError("setup must be called first")
        return self.pp, self.msk
