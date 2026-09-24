# Anonymous artifact notes

This repository is an anonymized research artifact for double-blind review.

## Reproduction scope

- `configs/paper/`: main MNIST and CIFAR-10 configurations.
- `configs/scalability/`: client/aggregator sweeps.
- `src/crosfed/crypto/`: the threshold MCFE reconstruction.
- `src/crosfed/orchestration/`: end-to-end secure aggregation.
- `contracts/`: four ChainMaker/EVM contract procedures.
- `tests/`: unit, negative-security, serialization, and secure-round tests.

The exact neural-network layer layouts and several training hyperparameters are
not specified in the manuscript. Parameter-count-exact candidate models and all
calibrated assumptions are documented in `docs/FIDELITY_AUDIT.md`.

## Reviewer quick check

```bash
python -m pip install -e '.[ml,test]'
pytest -q
python scripts/run_crypto_sanity.py --config configs/sanity_crypto.yaml
```

For the full one-round encrypted MNIST gate:

```bash
python scripts/run_federated.py \
  --config configs/paper/mnist_crypto_5c_3a_1r.yaml \
  --output runs/R006_mnist_crypto_5c_3a_1r_candidate_b/result.json
```

No author names, affiliations, personal accounts, private server addresses, or
original repository history are included in this snapshot.
