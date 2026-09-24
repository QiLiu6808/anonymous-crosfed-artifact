# Initial Experiment Results

**Date**: 2026-09-22  
**Plan**: `refine-logs/EXPERIMENT_PLAN_20260922.md`

## Results by Milestone

### M0: Crypto sanity — PASSED

| Run | Setting | Result | Status |
|---|---|---|---|
| R001 | SS512, n=3, s=3, t=2, η=4, committee={1,3} | recovered `[3,7,5,1]`, exactly equal to plaintext oracle | DONE |
| R002 | t-1, duplicate signer, tampered numerator, cross-round replay | all four invalid cases rejected before plaintext release | DONE |

Additional measurements:

- Wall time: 0.2173 s.
- Ciphertext group-element payload: 720 bytes per client for four coordinates.
- Partial-share group-element payload: 1,800 bytes per aggregator.
- SS512 is retained for paper fidelity; Charm reports that it provides roughly 80-bit security and is not a production recommendation.

### M1: Plain FL sanity — PASSED

| Run | Setting | Initial | After one round | Status |
|---|---|---|---|---|
| R003 | MNIST subset, IID, 2 clients, TinyCNN, CUDA | acc 10.64%, loss 2.3018 | acc 62.99%, loss 1.7137 | DONE |

- Training samples: 2,048; evaluation labels are MNIST ground truth for 1,024 test samples.
- Train/evaluate wall time after data download: 0.7801 s.
- The 9,098-parameter TinyCNN is a pipeline sanity model only. It is not reported as the paper's 19,518-parameter CNN.

### M1 calibration: 19,518-parameter CNN candidates

The manuscript does not specify the CNN layers. Three two-convolution candidates were derived that reach 19,518 parameters through active layers only; no unused padding parameters are present.

| Candidate | Conv channels | Hidden width | One-round accuracy | One-round loss |
|---|---:|---:|---:|---:|
| A | 10 → 40 | 8 | 46.78% | 1.4229 |
| B | 13 → 16 | 22 | **62.01%** | **1.0788** |
| C | 19 → 27 | 11 | 41.41% | 1.6171 |

All candidates used the same 2,048-sample IID subset, two clients, seed, normalization and SGD configuration on CPU. Candidate B is selected as the current auditable reconstruction for R004; this selection is a calibrated assumption, not evidence that it is the authors' unpublished architecture.

## Summary

- 3/12 tracked must-run experiments completed; R004 is queued after model calibration.
- M0 correctness gate: passed.
- M1 execution/data/metric gate: passed.
- Main paper result: not yet available; model architecture and missing optimizer/split details remain under fidelity audit.
- Ready for full crypto-FL: not yet. The paper-sized model, tensor codec, and chunked parameter path must be completed first.

## Next Step

1. Resolve or explicitly calibrate the 19,518-parameter MNIST CNN and 73,198-parameter CIFAR-10 MicroNet.
2. Add deterministic model flatten/unflatten plus tensor-level fixed-point bounds.
3. Run one full MNIST model vector through tMCFE and compare against the quantized FedAvg oracle.
