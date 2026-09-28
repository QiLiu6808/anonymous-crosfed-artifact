# CrosFed reproduction

Clean-room reconstruction of the experiments described in *CrosFed:
Privacy-Preserving Cross-Chain Federated Learning with Threshold Aggregation*.
All generated source, configuration, documentation, and result files live in
this `CrosFed` directory.

The repository uses a standard `src/` layout. Reusable implementation lives in
`src/crosfed`; `scripts/*.py` are backward-compatible wrappers only. See
[`docs/CODE_STRUCTURE.md`](docs/CODE_STRUCTURE.md) for module boundaries and a
change-location guide.

## What is implemented

- Exact-integer vector tMCFE reference path over Charm SS512: setup, client-key
  distribution, functional-share generation, encryption, share decryption, and
  threshold combination.
- Signed, round-bound envelopes; replay/duplicate checks; deterministic model
  flattening; signed fixed-point encoding; plaintext-oracle comparison.
- Plain FedAvg and encrypted FL runners for MNIST and CIFAR-10.
- Parameter-count-exact provisional models: 19,518 parameters for MNIST and
  73,198 for CIFAR-10. The paper does not disclose the exact layer layouts.
- Client-count and aggregator-count sweep generation.
- Clean-room HybridAlpha and PrivLDFL comparison adapters. They are explicitly
  labelled reconstructions because the baseline artifact/protocol details needed
  for byte-for-byte reproduction are unavailable.
- In-memory ledger/relay backend, ChainMaker subprocess adapter, CMC bridge, and
  four Solidity contracts corresponding to the paper's upload/download flows.
- JSONL phase metrics, incremental result files, runtime metadata, and split
  manifests, raw dataset-content hashes, and fixed-point clipping diagnostics.
- Adversarial protocol sanity CLI, three-seed repetition matrices, and a full
  two-direction ChainMaker upload/query/relay/fulfill driver.

See `docs/FIDELITY_AUDIT.md` before interpreting any number as a paper result.

## Remote environment

```bash
cd /path/to/CrosFed
source ./remote_env.sh
python -m pip install -e '.[ml,test]'
```

`remote_env.sh` activates `${CROSFED_CONDA_ENV:-projects-crypto}` and exposes
the PBC shared-library path required by Charm. Override `CONDA_ROOT` or
`CROSFED_PBC_LIB` when needed. SS512 emits an approximately 80-bit security
warning; it is retained solely because the manuscript specifies it.

Editable installation exposes stable commands such as `crosfed-train`,
`crosfed-sweep`, `crosfed-security`, `crosfed-summarize`, and the
`crosfed-chainmaker-*` tools. Every Python entry point can also be invoked as a
module, for example `python -m crosfed.cli.train`. Commands under `scripts/`
remain supported for existing reproduction instructions.

## Unified runner

Plain MNIST:

```bash
crosfed-train \
  --config configs/paper/mnist_plain_5c_30r.yaml \
  --output runs/R004_mnist_plain_5c_30r_candidate_b/result.json
```

One-round encrypted gate:

```bash
crosfed-train \
  --config configs/paper/mnist_crypto_5c_3a_1r.yaml \
  --output runs/R006_mnist_crypto_5c_3a_1r_candidate_b/result.json
```

Each completed round atomically updates `checkpoint.pt` beside the result. Resume
the same configuration with `--resume`; the runner verifies the configuration
digest and restores model plus Python/NumPy/PyTorch RNG state.

Background launch (only after the test gate passes):

```bash
bash scripts/launch_remote.sh crosfed_r006 \
  configs/paper/mnist_crypto_5c_3a_1r.yaml \
  runs/R006_mnist_crypto_5c_3a_1r_candidate_b/result.json
```

Generate, but do not execute, a sweep:

```bash
crosfed-sweep \
  --sweep configs/scalability/mnist_clients.yaml \
  --output-root runs --dry-run
```

Aggregate every completed run into paper-oriented JSON/CSV statistics:

```bash
crosfed-summarize \
  --results "runs/**/result.json" \
  --output-prefix runs/summary/paper_metrics
```

Runs are grouped by dataset, method, model, client count, aggregator count, and
threshold. The summary reports mean and sample standard deviation across seeds;
missing paper-level evidence remains empty instead of being inferred.

Generate a three-seed batch without executing it:

```bash
crosfed-sweep \
  --sweep configs/repetitions/mnist_crypto.yaml \
  --output-root runs --dry-run
```

Run protocol attack/replay/tamper checks (requires the Charm environment):

```bash
crosfed-security \
  --output runs/R020_adversarial_sanity/result.json
```

## ChainMaker

Copy `chainmaker/config/example.yaml`, then set the real CMC executable and SDK
configuration paths. The Python ledger adapter expects the bridge to return
normalized JSON envelopes for contract queries. CMC/EVM return-value encoding is
version-specific, so the supplied bridge deliberately fails instead of guessing
when it cannot locate normalized `envelopes`.

Generate a concrete three-chain config and deploy each contract to its intended
chain:

```bash
crosfed-chainmaker-config \
  --cmc /opt/chainmaker/cmc \
  --institution-sdk /etc/chainmaker/institution.yml \
  --aggregator-sdk /etc/chainmaker/aggregator.yml \
  --relay-sdk /etc/chainmaker/relay.yml \
  --output chainmaker/config/deployment.yaml --check-paths
bash scripts/deploy_chainmaker_multichain.sh /opt/chainmaker/cmc \
  /etc/chainmaker/institution.yml /etc/chainmaker/aggregator.yml \
  /etc/chainmaker/relay.yml
crosfed-chainmaker-e2e \
  --config chainmaker/config/deployment.yaml --payload-bytes 1024 \
  --output runs/R012_chainmaker_e2e/result.json
```

Contract microbenchmark:

```bash
crosfed-contract-bench \
  --config chainmaker/config/example.yaml \
  --payload-bytes 1024 --repetitions 5 \
  --output runs/R011_contract_microbench/result.json
```

The example ChainMaker paths are placeholders and are not evidence of a completed
deployment. Inline-payload gas and content-addressed-payload gas must be reported
separately.

## Test gate

Tests are defined for codec bounds, model parameter counts, state serialization,
signed envelopes, ledger routing, CRT packing, tMCFE negative cases, and the full
secure-round oracle. Run them later as one gate with:

```bash
pytest
```

No paper-scale experiment should be labelled successful until that gate and the
one-round encrypted pilot both pass.
