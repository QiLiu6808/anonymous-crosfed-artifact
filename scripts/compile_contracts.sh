#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="$project_dir/contracts/build"
mkdir -p "$output_dir"

for source in \
  EncryptedUpdateRegistry.sol \
  EncryptedUpdateRelay.sol \
  PartialUpdateRegistry.sol \
  PartialUpdateRelay.sol; do
  solc --optimize --abi --bin --overwrite \
    -o "$output_dir" "$project_dir/contracts/$source"
done

echo "contract artifacts written to $output_dir"
