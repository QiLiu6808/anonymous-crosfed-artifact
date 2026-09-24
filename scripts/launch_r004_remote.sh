#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
source ./remote_env.sh
mkdir -p logs runs/R004_mnist_plain_5c_30r_candidate_b

CUDA_VISIBLE_DEVICES=0 python scripts/run_federated.py \
  --config configs/paper/mnist_plain_5c_30r.yaml \
  --output runs/R004_mnist_plain_5c_30r_candidate_b/result.json \
  2>&1 | tee logs/R004_mnist_plain_5c_30r_candidate_b.log
