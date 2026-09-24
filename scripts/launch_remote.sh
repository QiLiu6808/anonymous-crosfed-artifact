#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 <screen-session> <config.yaml> <output.json>" >&2
  exit 2
fi

session_name="$1"
config_path="$2"
output_path="$3"
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_path="logs/${session_name}.log"

cd "$project_dir"
mkdir -p "$(dirname "$output_path")" logs

# screen owns the long-lived shell. remote_env.sh activates the declared conda
# environment and the Charm/PBC runtime before Python starts.
screen -dmS "$session_name" bash -lc "cd '$project_dir' && source ./remote_env.sh && CUDA_VISIBLE_DEVICES=0 python scripts/run_federated.py --config '$config_path' --output '$output_path' 2>&1 | tee '$log_path'"

echo "started screen session: $session_name"
echo "log: $project_dir/$log_path"
