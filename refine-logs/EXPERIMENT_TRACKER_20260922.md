# Experiment Tracker

| Run ID | Milestone | Purpose | System / Variant | Split | Metrics | Priority | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| R001 | M0 | tMCFE known-answer | tiny vector, n=3 s=3 t=2 | synthetic | exact equality | MUST | DONE | `[3,7,5,1]` exact match；0.217 s |
| R002 | M0 | threshold negatives | t-1/replay/tamper/duplicate | synthetic | reject reason | MUST | DONE | 4/4 非法情况均拒绝 |
| R003 | M1 | pipeline sanity | plain MNIST, 2 clients, 1 round | IID | acc/loss/digest | MUST | DONE | CUDA；accuracy 10.64% → 62.99%；loss 2.302 → 1.714 |
| R004 | M1 | MNIST baseline | plain CNN, 5 clients, 30 rounds | IID provisional | acc/loss | MUST | STOPPED | 候选 B；2026-09-22 按用户要求停止，不将部分运行计作结果 |
| R005 | M1 | CIFAR baseline | plain MicroNet, 5 clients, 100 rounds | TBD | acc/loss | MUST | TODO | 参数量 73,198 |
| R006 | M2 | encrypted single round | crypto-sim MNIST | same as R004 | oracle equality/time/bytes | MUST | DONE | 19,518 coordinates; exact oracle match; 617.86 s |
| R007 | M2 | encrypted MNIST | crypto-sim, 5/3/t | same as R004 | curves/time/bytes | MUST | TODO | pilot gate |
| R008 | M3 | client sweep | n=2..10, s=3 | paper-aligned | all paper metrics | MUST | TODO | one config at a time |
| R009 | M3 | aggregator sweep | n=5, s=1..5 | paper-aligned | all paper metrics | MUST | TODO | clarify t per s |
| R010 | M3 | baseline comparison | HybridAlpha/PrivLDFL/CrosFed | paper-aligned | all paper metrics | MUST | TODO | same hardware |
| R011 | M4 | contract microbench | four operations, inline | synthetic | gas/latency | MUST | TODO | reproduce table |
| R012 | M4 | cross-chain e2e | inline full update | MNIST one round | receipts/bytes/time | MUST | TODO | report inline mode; any content-addressed follow-up is separate |

## Implementation checkpoint (2026-09-22)

- R004-R010 configuration and runner code: READY FOR DEFERRED TEST GATE.
- R011 four-operation contracts and microbenchmark driver: CODE READY; real CMC paths and deployed addresses remain required.
- R012 ChainMaker ledger adapter path: CODE READY WITH EXTERNAL DEPLOYMENT BLOCKER; the version-specific CMC query result must be normalized to signed envelopes.
- No experiment was launched during this code-completion phase, following the user's instruction to test uniformly after implementation.
