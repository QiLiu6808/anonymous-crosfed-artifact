#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: $0 <cmc> <institution-sdk> <aggregator-sdk> <relay-sdk>" >&2
  exit 2
fi

cmc="$1"
institution_sdk="$2"
aggregator_sdk="$3"
relay_sdk="$4"
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_dir="$project_dir/contracts/build"

deploy() {
  local contract="$1"
  local sdk="$2"
  "$cmc" client contract user create \
    --contract-name="$contract" --runtime-type=EVM \
    --byte-code-path="$build_dir/${contract}.bin" \
    --abi-file-path="$build_dir/${contract}.abi" \
    --version=1.0 --sdk-conf-path="$sdk" --sync-result=true
}

deploy EncryptedUpdateRegistry "$institution_sdk"
deploy PartialUpdateRegistry "$aggregator_sdk"
deploy EncryptedUpdateRelay "$relay_sdk"
deploy PartialUpdateRelay "$relay_sdk"
