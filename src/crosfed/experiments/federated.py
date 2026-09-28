from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import struct
import time
from pathlib import Path

import torch
import numpy as np
import yaml
from torch.utils.data import Subset
from torchvision import datasets, transforms

from crosfed.baselines import PrivLDFLReconstruction, hybridalpha_profile
from crosfed.config import validate_experiment_config
from crosfed.crypto import FixedPointCodec, HMACSignatureProvider
from crosfed.ledger import ChainMakerLedger, RoutedRelay, SubprocessChainMakerClient
from crosfed.metrics import EventRecorder, MetricEvent
from crosfed.ml import (
    build_image_model,
    dataset_content_manifest,
    evaluate,
    fedavg,
    partition_iid,
    train_local,
)
from crosfed.ml.federated import seed_everything
from crosfed.orchestration import SecureRoundOrchestrator


def load_datasets(config: dict):
    dataset = config["dataset"]
    if dataset == "mnist":
        steps = [transforms.ToTensor()]
        if config.get("normalize", True):
            steps.append(transforms.Normalize((0.1307,), (0.3081,)))
        transform = transforms.Compose(steps)
        train = datasets.MNIST(config["data_dir"], train=True, download=True, transform=transform)
        test = datasets.MNIST(config["data_dir"], train=False, download=True, transform=transform)
    elif dataset == "cifar10":
        train_steps = []
        if config.get("augment", False):
            train_steps.extend([transforms.RandomCrop(32, padding=4), transforms.RandomHorizontalFlip()])
        train_steps.append(transforms.ToTensor())
        test_steps = [transforms.ToTensor()]
        if config.get("normalize", True):
            normalization = transforms.Normalize(
                (0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616)
            )
            train_steps.append(normalization)
            test_steps.append(normalization)
        train = datasets.CIFAR10(
            config["data_dir"], train=True, download=True,
            transform=transforms.Compose(train_steps),
        )
        test = datasets.CIFAR10(
            config["data_dir"], train=False, download=True,
            transform=transforms.Compose(test_steps),
        )
    else:
        raise ValueError(f"unsupported dataset: {dataset}")
    train_limit = min(int(config.get("train_samples", len(train))), len(train))
    test_limit = min(int(config.get("test_samples", len(test))), len(test))
    return Subset(train, range(train_limit)), Subset(test, range(test_limit))


def write_progress(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def config_digest(config: dict) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def rng_state() -> dict:
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
    }


def restore_rng_state(state: dict) -> None:
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch"])
    if state.get("cuda") is not None and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(state["cuda"])


def write_checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def load_checkpoint(path: Path) -> dict:
    try:
        return torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:  # PyTorch 1.10 compatibility target
        return torch.load(path, map_location="cpu")


def split_manifest(client_data: list[Subset]) -> dict:
    clients = []
    combined = hashlib.sha256()
    for client_id, subset in enumerate(client_data, start=1):
        digest = hashlib.sha256()
        for index in subset.indices:
            encoded = struct.pack(">Q", int(index))
            digest.update(encoded)
            combined.update(struct.pack(">I", client_id))
            combined.update(encoded)
        clients.append(
            {"client_id": client_id, "samples": len(subset), "indices_sha256": digest.hexdigest()}
        )
    return {"strategy": "iid-strided-after-seeded-permutation", "clients": clients, "sha256": combined.hexdigest()}


def runtime_manifest(device: torch.device) -> dict:
    value = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torchvision": __import__("torchvision").__version__,
        "device": str(device),
        "cuda_runtime": torch.version.cuda,
    }
    if device.type == "cuda":
        value["gpu"] = torch.cuda.get_device_name(device)
    return value


def summarize_round_evidence(
    recorder: EventRecorder,
    round_id: int,
    protocol: dict | None,
) -> dict:
    phase_exact: dict[str, dict[str, float]] = {}
    for event in recorder.events:
        if event.round_id != round_id:
            continue
        actor = phase_exact.setdefault(event.actor_id, {})
        actor[event.phase] = actor.get(event.phase, 0.0) + event.wall_seconds

    client_compute: dict[str, float] = {}
    aggregator_compute: dict[str, float] = {}
    for actor_id, phases in phase_exact.items():
        if actor_id.startswith("institution:"):
            client_compute[actor_id] = sum(
                phases.get(phase, 0.0)
                for phase in ("local_train", "encode", "encrypt")
            )
        elif actor_id.startswith("aggregator:"):
            aggregator_compute[actor_id] = phases.get("share_decrypt", 0.0)

    def aggregate(values: dict[str, float]) -> tuple[float | None, float | None]:
        samples = list(values.values())
        if not samples:
            return None, None
        return sum(samples) / len(samples), max(samples)

    client_mean, client_max = aggregate(client_compute)
    aggregator_mean, aggregator_max = aggregate(aggregator_compute)
    paper_derived = {
        "client_compute_seconds_by_id": client_compute,
        "client_compute_seconds_mean": client_mean,
        "client_compute_seconds_max": client_max,
        "aggregator_compute_seconds_by_id": aggregator_compute,
        "aggregator_compute_seconds_mean": aggregator_mean,
        "aggregator_compute_seconds_max": aggregator_max,
        "institution_combine_seconds": phase_exact.get("institutions", {}).get(
            "combine_decrypt", 0.0
        ),
    }
    if protocol is not None:
        paper_derived.update(
            {
                "client_upload_crypto_bytes_by_id": protocol[
                    "client_crypto_bytes_by_id"
                ],
                "client_upload_wire_bytes_by_id": protocol[
                    "client_wire_bytes_by_id"
                ],
                "client_download_crypto_bytes_per_institution": sum(
                    protocol["aggregator_crypto_bytes_by_id"]
                ),
                "client_download_wire_bytes_per_institution": protocol[
                    "aggregator_wire_bytes"
                ],
                "active_aggregators": len(protocol["aggregator_crypto_bytes_by_id"]),
                "threshold": protocol["threshold"],
            }
        )
    return {"phase_exact_seconds": phase_exact, "paper_derived": paper_derived}


def write_round_metrics(path: Path, rounds: list[dict]) -> None:
    fields = [
        "round",
        "learning_rate",
        "accuracy",
        "loss",
        "client_compute_seconds_mean",
        "client_compute_seconds_max",
        "aggregator_compute_seconds_mean",
        "aggregator_compute_seconds_max",
        "client_download_crypto_bytes_per_institution",
        "client_download_wire_bytes_per_institution",
        "active_aggregators",
        "threshold",
        "exact_oracle_match",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in rounds:
            derived = record.get("evidence", {}).get("paper_derived", {})
            protocol = record.get("protocol") or {}
            writer.writerow(
                {
                    "round": record["round"],
                    "learning_rate": record["learning_rate"],
                    "accuracy": record["accuracy"],
                    "loss": record["loss"],
                    "client_compute_seconds_mean": derived.get(
                        "client_compute_seconds_mean"
                    ),
                    "client_compute_seconds_max": derived.get(
                        "client_compute_seconds_max"
                    ),
                    "aggregator_compute_seconds_mean": derived.get(
                        "aggregator_compute_seconds_mean"
                    ),
                    "aggregator_compute_seconds_max": derived.get(
                        "aggregator_compute_seconds_max"
                    ),
                    "client_download_crypto_bytes_per_institution": derived.get(
                        "client_download_crypto_bytes_per_institution"
                    ),
                    "client_download_wire_bytes_per_institution": derived.get(
                        "client_download_wire_bytes_per_institution"
                    ),
                    "active_aggregators": derived.get("active_aggregators"),
                    "threshold": derived.get("threshold"),
                    "exact_oracle_match": protocol.get("exact_oracle_match"),
                }
            )
    temporary.replace(path)


def chainmaker_backend(config: dict, aggregators: int) -> dict:
    path = Path(config["chainmaker_config"])
    chain_config = yaml.safe_load(path.read_text(encoding="utf-8"))
    bridge = chain_config["sdk_bridge"]
    client = SubprocessChainMakerClient(
        command=[str(item) for item in bridge["command"]],
        timeout_seconds=float(bridge.get("timeout_seconds", 120)),
    )
    institution = chain_config["institution_chain"]
    aggregator = chain_config["aggregator_chain"]
    identities = [f"institution:{i}" for i in range(1, int(config["clients"]) + 1)] + [
        f"aggregator:{i}" for i in range(1, aggregators + 1)
    ]
    signer = HMACSignatureProvider.generate(identities)
    institution_ledger = ChainMakerLedger(
        institution["chain_id"], institution["contract"], client,
        institution["submit_method"], institution["query_method"], signer,
    )
    aggregator_ledger = ChainMakerLedger(
        aggregator["chain_id"], aggregator["contract"], client,
        aggregator["submit_method"], aggregator["query_method"], signer,
    )
    relay = RoutedRelay(
        [institution_ledger, aggregator_ledger],
        {
            (aggregator_ledger.chain_id, institution_ledger.chain_id),
            (institution_ledger.chain_id, aggregator_ledger.chain_id),
        },
    )
    return {
        "signer": signer,
        "institution_ledger": institution_ledger,
        "aggregator_ledger": aggregator_ledger,
        "relay": relay,
    }


def round_learning_rate(config: dict, round_id: int) -> float:
    learning_rate = float(config["learning_rate"])
    schedule = config.get("lr_schedule", {})
    if schedule.get("type", "constant") == "constant":
        return learning_rate
    if schedule["type"] == "step":
        gamma = float(schedule.get("gamma", 0.1))
        milestones = [int(value) for value in schedule.get("milestones", [])]
        return learning_rate * gamma ** sum(round_id > milestone for milestone in milestones)
    raise ValueError(f"unsupported lr schedule: {schedule['type']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--checkpoint")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    validate_experiment_config(config)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path = Path(args.checkpoint) if args.checkpoint else output.parent / "checkpoint.pt"
    experiment_config_digest = config_digest(config)
    seed_everything(int(config["seed"]))
    device = torch.device(config.get("device", "cuda") if torch.cuda.is_available() else "cpu")
    train_data, test_data = load_datasets(config)
    client_data = partition_iid(train_data, int(config["clients"]), int(config["seed"]))
    data_manifest = split_manifest(client_data)
    data_manifest["train_dataset"] = dataset_content_manifest(train_data)
    data_manifest["test_dataset"] = dataset_content_manifest(test_data)
    model = build_image_model(
        config["dataset"], config.get("model", "paper_candidate"), config.get("candidate", "b")
    )
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    initial = evaluate(model, test_data, int(config["batch_size"]), device)
    runtime = runtime_manifest(device)
    (output.parent / "resolved_config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    (output.parent / "environment.json").write_text(
        json.dumps(runtime, indent=2), encoding="utf-8"
    )
    (output.parent / "split_manifest.json").write_text(
        json.dumps(data_manifest, indent=2), encoding="utf-8"
    )
    events_path = output.parent / "events.jsonl"
    recorder = EventRecorder(events_path, truncate=not args.resume)
    secure_orchestrator = None
    privldfl_orchestrator = None
    baseline_metadata = None
    mode = config["mode"]
    crypto_config = config.get("codec", {"scale": 1000, "clip": 8.0})
    codec = FixedPointCodec(
        scale=int(crypto_config["scale"]),
        clip=float(crypto_config["clip"]),
    )
    if mode in {"crypto", "hybridalpha"}:
        if mode == "hybridalpha":
            profile = hybridalpha_profile()
            aggregators = profile.aggregators
            threshold = profile.threshold
            committee = list(profile.committee)
            baseline_metadata = {
                "name": "HybridAlpha",
                "implementation_status": profile.implementation_status,
            }
        else:
            aggregators = int(config["aggregators"])
            threshold = int(config["threshold"])
            committee = config.get("committee")
        backend = config.get("ledger_backend", "memory")
        backend_arguments = {}
        if backend == "chainmaker":
            backend_arguments = chainmaker_backend(config, aggregators)
        elif backend != "memory":
            raise ValueError("ledger_backend must be memory or chainmaker")
        secure_orchestrator = SecureRoundOrchestrator(
            experiment_id=config["run_id"],
            template_state=model.state_dict(),
            clients=int(config["clients"]),
            aggregators=aggregators,
            threshold=threshold,
            codec=codec,
            group_name=config.get("group", "SS512"),
            recorder=recorder,
            **backend_arguments,
        )
        if baseline_metadata is None:
            baseline_metadata = {"ledger_backend": backend}
        else:
            baseline_metadata["ledger_backend"] = backend
    elif mode == "privldfl":
        privldfl_orchestrator = PrivLDFLReconstruction(
            model.state_dict(),
            codec,
            block_size=int(config.get("crt_block_size", 32)),
        )
        baseline_metadata = {
            "name": "PrivLDFL",
            "implementation_status": "clean-room-crt-reconstruction",
        }
        committee = None
    elif mode == "plain":
        committee = None
    else:
        raise ValueError("mode must be plain, crypto, hybridalpha, or privldfl")

    rounds: list[dict] = []
    start_round = 1
    prior_wall_seconds = 0.0
    if args.resume:
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"resume checkpoint not found: {checkpoint_path}")
        checkpoint = load_checkpoint(checkpoint_path)
        if checkpoint["config_digest"] != experiment_config_digest:
            raise ValueError("checkpoint configuration does not match current config")
        model.load_state_dict(checkpoint["model_state"])
        rounds = list(checkpoint["rounds"])
        start_round = int(checkpoint["next_round"])
        prior_wall_seconds = float(checkpoint.get("wall_seconds", 0.0))
        restore_rng_state(checkpoint["rng_state"])
    started = time.perf_counter()
    for round_id in range(start_round, int(config["rounds"]) + 1):
        current_learning_rate = round_learning_rate(config, round_id)
        local_states = []
        local_losses = []
        for client_id, dataset in enumerate(client_data, start=1):
            local_started = time.perf_counter()
            state, loss = train_local(
                model,
                dataset,
                int(config["local_epochs"]),
                int(config["batch_size"]),
                current_learning_rate,
                device,
                optimizer_name=config.get("optimizer", "sgd"),
                momentum=float(config.get("momentum", 0.9)),
                weight_decay=float(config.get("weight_decay", 0.0)),
            )
            local_states.append(state)
            local_losses.append(loss)
            recorder.record(
                MetricEvent(
                    config["run_id"], "local_train", f"institution:{client_id}",
                    round_id, time.perf_counter() - local_started,
                )
            )
        sample_counts = [len(dataset) for dataset in client_data]
        protocol_metrics = None
        if secure_orchestrator is not None:
            secure_result = secure_orchestrator.aggregate(
                local_states,
                sample_counts,
                round_id,
                committee=committee,
                dlog_bound=config.get("dlog_bound"),
            )
            global_state = secure_result.global_state
            protocol_metrics = {
                "exact_oracle_match": secure_result.exact_oracle_match,
                "client_wire_bytes": secure_result.client_wire_bytes,
                "aggregator_wire_bytes": secure_result.aggregator_wire_bytes,
                "client_wire_bytes_by_id": secure_result.client_wire_bytes_by_id,
                "aggregator_wire_bytes_by_id": secure_result.aggregator_wire_bytes_by_id,
                "client_crypto_bytes_by_id": secure_result.client_crypto_bytes_by_id,
                "aggregator_crypto_bytes_by_id": secure_result.aggregator_crypto_bytes_by_id,
                "round_context_digest": secure_result.round_context.digest,
                "committee": list(secure_result.round_context.committee),
                "threshold": secure_result.round_context.threshold,
                "quantization_diagnostics_by_client": [
                    item.to_dict()
                    for item in secure_result.quantization_diagnostics_by_client
                ],
            }
        elif privldfl_orchestrator is not None:
            privldfl_result = privldfl_orchestrator.aggregate(local_states, sample_counts)
            global_state = privldfl_result.global_state
            protocol_metrics = {
                "exact_roundtrip": privldfl_result.exact_roundtrip,
                "client_wire_bytes": privldfl_result.client_wire_bytes,
                "implementation_status": privldfl_result.implementation_status,
            }
        else:
            global_state = fedavg(local_states, sample_counts)
        model.load_state_dict(global_state)
        evaluation = evaluate(model, test_data, int(config["batch_size"]), device)
        record = {
            "round": round_id,
            "learning_rate": current_learning_rate,
            "local_loss": local_losses,
            **evaluation,
            "protocol": protocol_metrics,
        }
        record["evidence"] = summarize_round_evidence(
            recorder, round_id, protocol_metrics
        )
        rounds.append(record)
        write_round_metrics(output.parent / "round_metrics.csv", rounds)
        progress = {
            "run_id": config["run_id"],
            "config": config,
            "config_digest": experiment_config_digest,
            "status": "running",
            "mode": config["mode"],
            "dataset": config["dataset"],
            "device": str(device),
            "model_parameters": parameter_count,
            "baseline": baseline_metadata,
            "runtime": runtime,
            "split": data_manifest,
            "initial": initial,
            "rounds": rounds,
            "wall_seconds": prior_wall_seconds + time.perf_counter() - started,
        }
        write_progress(output, progress)
        write_checkpoint(
            checkpoint_path,
            {
                "config_digest": experiment_config_digest,
                "next_round": round_id + 1,
                "model_state": model.state_dict(),
                "rounds": rounds,
                "rng_state": rng_state(),
                "wall_seconds": progress["wall_seconds"],
            },
        )
        print(json.dumps(record), flush=True)

    final = {
        "run_id": config["run_id"],
        "config": config,
        "config_digest": experiment_config_digest,
        "status": "passed",
        "mode": config["mode"],
        "dataset": config["dataset"],
        "device": str(device),
        "model_parameters": parameter_count,
        "baseline": baseline_metadata,
        "runtime": runtime,
        "split": data_manifest,
        "initial": initial,
        "rounds": rounds,
        "wall_seconds": prior_wall_seconds + time.perf_counter() - started,
    }
    write_progress(output, final)
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
