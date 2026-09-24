#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <cmc-executable> <sdk-config>" >&2
  exit 2
fi

cmc="$1"
sdk_config="$2"
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_dir="$project_dir/contracts/build"

for contract in \
  EncryptedUpdateRegistry \
  EncryptedUpdateRelay \
  PartialUpdateRegistry \
  PartialUpdateRelay; do
  "$cmc" client contract user create \
    --contract-name="$contract" \
    --runtime-type=EVM \
    --byte-code-path="$build_dir/${contract}.bin" \
    --abi-file-path="$build_dir/${contract}.abi" \
    --version=1.0 \
    --sdk-conf-path="$sdk_config" \
    --sync-result=true
done
