#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
conda_root="${CONDA_ROOT:-$HOME/miniconda3}"
conda_environment="${CROSFED_CONDA_ENV:-projects-crypto}"
pbc_library_dir="${CROSFED_PBC_LIB:-$project_dir/../../third_party/local/lib}"

source "$conda_root/etc/profile.d/conda.sh"
conda activate "$conda_environment"
export LD_LIBRARY_PATH="$pbc_library_dir:${LD_LIBRARY_PATH:-}"
export PYTHONUNBUFFERED=1
