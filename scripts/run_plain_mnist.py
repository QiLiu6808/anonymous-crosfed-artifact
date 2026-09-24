from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
import yaml
from torch.utils.data import Subset
from torchvision import datasets, transforms

from crosfed.ml import build_mnist_model, evaluate, fedavg, partition_iid, train_local
from crosfed.ml.federated import seed_everything


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default="runs/R003_plain_mnist_sanity/result.json")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    seed_everything(config["seed"])
    device = torch.device(config["device"] if torch.cuda.is_available() else "cpu")
    transform_steps = [transforms.ToTensor()]
    if config.get("normalize", False):
        transform_steps.append(transforms.Normalize((0.1307,), (0.3081,)))
    transform = transforms.Compose(transform_steps)
    train_full = datasets.MNIST(config["data_dir"], train=True, download=True, transform=transform)
    test_full = datasets.MNIST(config["data_dir"], train=False, download=True, transform=transform)
    train_data = Subset(train_full, range(min(config["train_samples"], len(train_full))))
    test_data = Subset(test_full, range(min(config["test_samples"], len(test_full))))
    client_data = partition_iid(train_data, config["clients"], config["seed"])
    model = build_mnist_model(config.get("model", "tiny"), config.get("candidate", "b"))
    initial = evaluate(model, test_data, config["batch_size"], device)
    rounds = []
    started = time.perf_counter()
    for round_id in range(1, config["rounds"] + 1):
        local_states = []
        local_losses = []
        for dataset in client_data:
            state, loss = train_local(
                model, dataset, config["local_epochs"], config["batch_size"],
                config["learning_rate"], device,
            )
            local_states.append(state)
            local_losses.append(loss)
        model.load_state_dict(fedavg(local_states, [len(item) for item in client_data]))
        metrics = evaluate(model, test_data, config["batch_size"], device)
        rounds.append({"round": round_id, "local_loss": local_losses, **metrics})
        progress = {
            "run_id": config["run_id"],
            "status": "running",
            "device": str(device),
            "model": config.get("model", "tiny"),
            "candidate": config.get("candidate"),
            "model_parameters": sum(parameter.numel() for parameter in model.parameters()),
            "initial": initial,
            "rounds": rounds,
            "wall_seconds": time.perf_counter() - started,
        }
        output.write_text(json.dumps(progress, indent=2), encoding="utf-8")
        print(json.dumps(rounds[-1]), flush=True)
    result = {
        "run_id": config["run_id"],
        "status": "passed" if rounds and all(torch.isfinite(torch.tensor(r["loss"])) for r in rounds) else "failed",
        "device": str(device),
        "model": config.get("model", "tiny"),
        "candidate": config.get("candidate"),
        "model_parameters": sum(parameter.numel() for parameter in model.parameters()),
        "initial": initial,
        "rounds": rounds,
        "wall_seconds": time.perf_counter() - started,
    }
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
