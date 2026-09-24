from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from functools import reduce
from typing import Sequence

import torch

from crosfed.crypto import (
    FixedPointCodec,
    HMACSignatureProvider,
    ThresholdMCFE,
    function_digest,
)
from crosfed.domain import (
    EnvelopeSigner,
    MessageKind,
    RoundContext,
    RoundPhase,
    RoundStateMachine,
    SignedEnvelope,
    canonical_json,
    sha256_hex,
)
from crosfed.ledger import InMemoryLedger, InMemoryRelay, LedgerPort, RelayPort
from crosfed.metrics import EventRecorder, PhaseTimer
from crosfed.ml import ModelVectorSpec, flatten_state_dict, unflatten_state_dict


@dataclass(frozen=True)
class SecureAggregationResult:
    global_state: OrderedDict[str, torch.Tensor]
    exact_oracle_match: bool
    encoded_weighted_sum: list[int]
    oracle_weighted_sum: list[int]
    round_context: RoundContext
    client_wire_bytes: int
    aggregator_wire_bytes: int
    client_wire_bytes_by_id: tuple[int, ...]
    aggregator_wire_bytes_by_id: tuple[int, ...]
    client_crypto_bytes_by_id: tuple[int, ...]
    aggregator_crypto_bytes_by_id: tuple[int, ...]
    phase: RoundPhase


def _model_spec_digest(spec: ModelVectorSpec) -> str:
    value = [
        {
            "name": tensor.name,
            "shape": list(tensor.shape),
            "dtype": str(tensor.dtype),
            "numel": tensor.numel,
        }
        for tensor in spec.tensors
    ]
    return sha256_hex(canonical_json(value))


def _reduced_integer_weights(sample_counts: Sequence[int]) -> list[int]:
    values = [int(value) for value in sample_counts]
    if not values or any(value <= 0 for value in values):
        raise ValueError("positive sample counts are required")
    divisor = reduce(math.gcd, values)
    return [value // divisor for value in values]


class SecureRoundOrchestrator:
    """Full model-vector tMCFE aggregation over ledger/relay ports.

    The current concrete ledger is the contract-faithful in-memory backend. The
    orchestrator intentionally depends only on commit/query behavior so the same
    flow can be wired to ChainMaker adapters.
    """

    def __init__(
        self,
        experiment_id: str,
        template_state: OrderedDict[str, torch.Tensor] | dict[str, torch.Tensor],
        clients: int,
        aggregators: int,
        threshold: int,
        codec: FixedPointCodec,
        group_name: str = "SS512",
        recorder: EventRecorder | None = None,
        signer: EnvelopeSigner | None = None,
        institution_ledger: LedgerPort | None = None,
        aggregator_ledger: LedgerPort | None = None,
        relay: RelayPort | None = None,
    ) -> None:
        if not 1 <= threshold <= aggregators:
            raise ValueError("threshold must be in [1, aggregators]")
        template_vector, self.model_spec = flatten_state_dict(template_state)
        self.experiment_id = experiment_id
        self.clients = clients
        self.aggregators = aggregators
        self.threshold = threshold
        self.codec = codec
        self.recorder = recorder or EventRecorder()
        self.model_digest = _model_spec_digest(self.model_spec)
        self.scheme = ThresholdMCFE(group_name)
        with PhaseTimer(self.recorder, experiment_id, "setup", "kgc", 0):
            self.scheme.setup(clients, template_vector.numel())
        identities = [f"institution:{i}" for i in range(1, clients + 1)] + [
            f"aggregator:{j}" for j in range(1, aggregators + 1)
        ]
        supplied = [signer is not None, institution_ledger is not None, aggregator_ledger is not None, relay is not None]
        if any(supplied) and not all(supplied):
            raise ValueError("signer, both ledgers, and relay must be supplied together")
        if all(supplied):
            self.signer = signer
            self.institution_ledger = institution_ledger
            self.aggregator_ledger = aggregator_ledger
            self.relay = relay
        else:
            self.signer = HMACSignatureProvider.generate(identities)
            self.institution_ledger = InMemoryLedger("institution-registry", self.signer)
            self.aggregator_ledger = InMemoryLedger("aggregator-registry", self.signer)
            self.relay = InMemoryRelay([self.institution_ledger, self.aggregator_ledger])

    def aggregate(
        self,
        states: Sequence[OrderedDict[str, torch.Tensor] | dict[str, torch.Tensor]],
        sample_counts: Sequence[int],
        round_id: int,
        committee: Sequence[int] | None = None,
        dlog_bound: int | None = None,
    ) -> SecureAggregationResult:
        if len(states) != self.clients or len(sample_counts) != self.clients:
            raise ValueError("one state and sample count are required per client")
        active_committee = tuple(
            sorted(committee or range(1, self.threshold + 1))
        )
        if len(active_committee) < self.threshold:
            raise ValueError("committee smaller than threshold")
        if any(identity < 1 or identity > self.aggregators for identity in active_committee):
            raise ValueError("committee identity out of range")

        machine = RoundStateMachine()
        machine.advance(RoundPhase.LOCAL_TRAINED)
        vectors: list[torch.Tensor] = []
        for state in states:
            vector, spec = flatten_state_dict(state)
            if spec != self.model_spec:
                raise ValueError("client model structure differs from template")
            vectors.append(vector)

        with PhaseTimer(
            self.recorder, self.experiment_id, "encode", "institutions", round_id
        ):
            encoded = [self.codec.encode(vector.tolist()) for vector in vectors]
        machine.advance(RoundPhase.ENCODED)

        integer_weights = _reduced_integer_weights(sample_counts)
        weight_matrix = [
            [integer_weights[i]] * self.model_spec.total_numel
            for i in range(self.clients)
        ]
        function_id = function_digest(weight_matrix)
        context = RoundContext(
            experiment_id=self.experiment_id,
            round_id=round_id,
            clients=self.clients,
            aggregators=self.aggregators,
            threshold=self.threshold,
            committee=active_committee,
            model_digest=self.model_digest,
            codec_id=f"fixed-point:{self.codec.scale}:{self.codec.clip}",
            function_digest=function_id,
        )
        with PhaseTimer(
            self.recorder, self.experiment_id, "generate_functional_keys", "kgc", round_id
        ):
            share_keys = self.scheme.generate_functional_keys(
                weight_matrix,
                range(1, self.aggregators + 1),
                self.threshold,
                round_id,
            )

        ciphertexts = []
        client_wire_bytes = 0
        client_wire_by_id = []
        client_crypto_by_id = []
        for index, vector in enumerate(encoded, start=1):
            actor = f"institution:{index}"
            with PhaseTimer(
                self.recorder, self.experiment_id, "encrypt", actor, round_id
            ) as timer:
                ciphertext = self.scheme.encrypt(
                    vector, self.scheme.encryption_key(index), round_id
                )
                timer.logical_bytes = len(vector) * 8
            ciphertexts.append(ciphertext)
            client_crypto_by_id.append(self.scheme.serialized_size(ciphertext))
            payload = self.scheme.ciphertext_to_payload(ciphertext)
            envelope = SignedEnvelope.create(
                MessageKind.ENCRYPTED_LOCAL_UPDATE,
                actor,
                context,
                payload,
                self.signer,
            )
            with PhaseTimer(
                self.recorder, self.experiment_id, "commit_encrypted_update", actor, round_id
            ) as timer:
                receipt = self.institution_ledger.commit(envelope)
                timer.wire_bytes = receipt.wire_bytes
            client_wire_bytes += receipt.wire_bytes
            client_wire_by_id.append(receipt.wire_bytes)
        machine.advance(RoundPhase.ENCRYPTED)
        machine.advance(RoundPhase.LOCAL_UPDATES_COMMITTED)
        machine.advance(RoundPhase.COMMITTEE_FROZEN)

        with PhaseTimer(
            self.recorder, self.experiment_id, "relay_encrypted_updates", "relay", round_id
        ):
            fetched_envelopes = self.relay.query(
                self.aggregator_ledger.chain_id,
                self.institution_ledger.chain_id,
                MessageKind.ENCRYPTED_LOCAL_UPDATE,
                context.digest,
            )
        if len(fetched_envelopes) != self.clients:
            raise ValueError("aggregator did not receive all client ciphertexts")
        fetched_ciphertexts = [
            self.scheme.ciphertext_from_payload(dict(envelope.payload))
            for envelope in fetched_envelopes
        ]

        aggregator_wire_bytes = 0
        aggregator_wire_by_id = []
        aggregator_crypto_by_id = []
        for aggregator_id in active_committee:
            actor = f"aggregator:{aggregator_id}"
            with PhaseTimer(
                self.recorder, self.experiment_id, "share_decrypt", actor, round_id
            ):
                share = self.scheme.share_decrypt(
                    fetched_ciphertexts,
                    weight_matrix,
                    share_keys[aggregator_id],
                    active_committee,
                    round_id,
                )
            aggregator_crypto_by_id.append(self.scheme.serialized_size(share))
            envelope = SignedEnvelope.create(
                MessageKind.PARTIAL_GLOBAL_UPDATE,
                actor,
                context,
                self.scheme.partial_share_to_payload(share),
                self.signer,
            )
            with PhaseTimer(
                self.recorder, self.experiment_id, "commit_partial_update", actor, round_id
            ) as timer:
                receipt = self.aggregator_ledger.commit(envelope)
                timer.wire_bytes = receipt.wire_bytes
            aggregator_wire_bytes += receipt.wire_bytes
            aggregator_wire_by_id.append(receipt.wire_bytes)
        machine.advance(RoundPhase.SHARES_COMPUTED)
        machine.advance(RoundPhase.SHARES_COMMITTED)

        with PhaseTimer(
            self.recorder, self.experiment_id, "relay_partial_updates", "relay", round_id
        ):
            partial_envelopes = self.relay.query(
                self.institution_ledger.chain_id,
                self.aggregator_ledger.chain_id,
                MessageKind.PARTIAL_GLOBAL_UPDATE,
                context.digest,
            )
        if len(partial_envelopes) < self.threshold:
            raise ValueError("threshold was not reached")
        machine.advance(RoundPhase.THRESHOLD_REACHED)
        partials = [
            self.scheme.partial_share_from_payload(dict(envelope.payload))
            for envelope in partial_envelopes
        ]

        oracle = [
            sum(encoded[i][z] * integer_weights[i] for i in range(self.clients))
            for z in range(self.model_spec.total_numel)
        ]
        required_bound = max(abs(x) for x in oracle)
        bound = dlog_bound if dlog_bound is not None else required_bound
        if bound < required_bound:
            raise ValueError(
                f"configured dlog bound {bound} is smaller than required {required_bound}"
            )
        with PhaseTimer(
            self.recorder, self.experiment_id, "combine_decrypt", "institutions", round_id
        ):
            recovered = self.scheme.combine(partials, round_id, bound)
        exact_match = recovered == oracle
        if not exact_match:
            raise ValueError("encrypted aggregation differs from integer plaintext oracle")
        machine.advance(RoundPhase.GLOBAL_DECRYPTED)

        weight_sum = sum(integer_weights)
        decoded_average = torch.tensor(
            [value / self.codec.scale / weight_sum for value in recovered],
            dtype=torch.float64,
        )
        global_state = unflatten_state_dict(decoded_average, self.model_spec)
        return SecureAggregationResult(
            global_state=global_state,
            exact_oracle_match=exact_match,
            encoded_weighted_sum=recovered,
            oracle_weighted_sum=oracle,
            round_context=context,
            client_wire_bytes=client_wire_bytes,
            aggregator_wire_bytes=aggregator_wire_bytes,
            client_wire_bytes_by_id=tuple(client_wire_by_id),
            aggregator_wire_bytes_by_id=tuple(aggregator_wire_by_id),
            client_crypto_bytes_by_id=tuple(client_crypto_by_id),
            aggregator_crypto_bytes_by_id=tuple(aggregator_crypto_by_id),
            phase=machine.phase,
        )
