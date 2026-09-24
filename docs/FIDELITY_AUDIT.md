# CrosFed Reproduction Fidelity Audit

**Date**: 2026-09-22  
**Status**: preliminary; updated before every paper-scale run

## Evidence classes

- **Specified**: explicitly stated in the supplied CrosFed manuscript.
- **Derived**: uniquely implied by formulas or reported dimensions.
- **Missing**: necessary for exact reproduction but absent from the manuscript.
- **Provisional**: engineering choice used only for sanity checks and never presented as a paper result.

## Machine-learning configuration

| Item | Paper evidence | Status | Reproduction action |
|---|---|---|---|
| MNIST model | CNN with 19,518 parameters | Specified only at family/count level | Require exact parameter-count assertion; architecture remains unresolved |
| CIFAR-10 model | MicroNet with 73,198 parameters; citation `LiCD0LY00V21` | Specified only at family/count level | Treat as a custom scaled/adapted MicroNet until artifact is found |
| Official cited MicroNet | The cited ICCV 2021 repository reports M0–M3 models with 1.0M–2.6M parameters | External cross-check | The paper's 73,198-parameter network is not an unmodified official M0–M3 model |
| Optimizer | Not stated | Missing | Calibrate SGD/Adam candidates; preserve every config |
| Local epochs and batch size | Not stated | Missing | Calibrate, never hard-code as paper fact |
| Learning rate/schedule | Only a symbolic `lr` appears | Missing | Calibrate from curves |
| Data preprocessing/augmentation | Not stated | Missing | Start with canonical normalization; ablate augmentation |
| Client split | Horizontal FL stated, IID/Non-IID not stated | Missing | Run IID first and record split manifest |
| Seeds | Not stated | Missing | Use fixed declared seeds; report mean/std where feasible |

The current `TinyMNISTCNN` has 9,098 parameters and is marked **pipeline sanity only**. Its R003 result must not be compared with the paper's 99.10% result.

## Cryptographic configuration

| Item | Paper evidence | Status | Reproduction action |
|---|---|---|---|
| Group | Charm-Crypto 0.5.0, SS512 | Specified | Implemented; Charm warns SS512 is about 80-bit security |
| Six tMCFE algorithms | Equations supplied | Specified | Implemented as a small-vector reference path |
| Threshold in 5-client/3-aggregator main run | Not stated | Missing | Do not infer silently; use explicit config and test candidate `t=2` first |
| Float-to-exponent encoding | Not stated | Missing | Explicit signed fixed-point codec with bound checks |
| Discrete-log table range and precomputation timing | Only lookup-table strategy stated | Missing | Record bound, build time, memory and whether precomputation is excluded |
| Randomizer notation | Manuscript writes `r_z` without client index | Ambiguous | Implement fresh randomness per client and coordinate, consistent with MCFE privacy/correctness |
| Committee `S` | Appears in Lagrange coefficient | Derived | Freeze `S` before ShareDecrypt; all shares in a combined result use the same `S` |

## Systems configuration

| Item | Paper evidence | Status | Reproduction action |
|---|---|---|---|
| Original runtime | Ubuntu 20.04, Python 3.8, PyTorch 1.10, CUDA 11.3 | Specified | Preserve as legacy target; current executable environment is recorded separately |
| Current remote runtime | Python 3.10, PyTorch 2.11, CUDA 12.8, RTX PRO 6000 | Observed | Use for primary reconstruction; attribute timing differences |
| PBC runtime | Charm extension initially cannot locate `libpbc.so.1` | Observed | `remote_env.sh` sets the verified library path |
| Full ciphertext storage | Manuscript says ciphertexts are stored on chain | Specified | Implement inline and content-addressed modes; never mix their gas figures |
| Gas table versus payload size | Roughly constant 0.9M gas while reported updates are multi-megabyte | Unresolved | Audit transaction payload and ChainMaker/EVM accounting before comparison |

## Run-release rule

A run may be labelled **paper reproduction** only if every configuration field is either specified, uniquely derived, or explicitly reported as a calibrated assumption. Runs using unresolved model architectures are labelled **sanity** or **provisional reconstruction**.

## Baseline fidelity

| Baseline | Available evidence | Implementation label | Prohibited claim |
|---|---|---|---|
| HybridAlpha | Manuscript description and reported aggregate metrics | `derived-single-aggregator-reconstruction` using the one-of-one MCFE specialization | Official HybridAlpha implementation or exact runtime reproduction |
| PrivLDFL | Published high-level description of decentralized MCFE, CRT compression, client partitioning, and reported aggregate metrics | `clean-room-crt-reconstruction`; exact signed CRT roundtrip and communication accounting | Official PrivLDFL wire format, modulus schedule, or cryptographic equivalence |

Baseline curves are useful as accuracy-compatible controls. Their computation and
communication numbers must remain labelled as reconstruction results unless the
authors' original source and complete parameters are recovered.

## ChainMaker readiness

The repository contains four Solidity contracts, a ledger port, a subprocess CMC
adapter, a routed relay, and a gas microbenchmark driver. The checked-in CMC paths
are examples. A result becomes a real-chain result only after contract deployment,
SDK identity binding, version-specific ABI/result decoding, and receipt inspection
are recorded in the run directory.

## External provenance

- Official cited MicroNet paper: https://openaccess.thecvf.com/content/ICCV2021/html/Li_MicroNet_Improving_Image_Recognition_With_Extremely_Low_FLOPs_ICCV_2021_paper.html
- Official MicroNet implementation: https://github.com/liyunsheng13/micronet
