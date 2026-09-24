# Experiment Plan

**Problem**: 从论文正文完整复现 CrosFed 的模型质量、tMCFE 阈值聚合、扩展性、基线和跨链 gas 结果。  
**Method Thesis**: 轮次绑定的向量 tMCFE 与多聚合器阈值解密能在不暴露单机构更新的情况下实现跨链加权联邦聚合。  
**Date**: 2026-09-22

## Claim Map

| Claim | Why It Matters | Minimum Convincing Evidence | Linked Blocks |
|---|---|---|---|
| C1：CrosFed 的加密路径保持 FL 聚合语义和模型质量 | 支撑方法可用性 | 每轮加密结果与量化明文 oracle 等价；MNIST/CIFAR-10 曲线接近论文 | B1, B2 |
| C2：阈值和跨链机制提供可执行的去单点、轮次隔离与可追溯性 | 支撑核心系统贡献 | `t` 份额成功、`t-1` 失败；重放/篡改失败；四合约流程和 receipts/gas 完整 | B3, B5 |
| Anti-claim：论文开销数字不是计时口径、序列化或 mock 造成 | 排除伪效率 | phase timer、wire bytes、真实群运算、真实链与内存链分开报告 | B4, B5 |

## Paper Storyline

- Main paper must prove: B1 正确性、B2 主结果、B3 阈值安全行为、B4 扩展趋势、B5 跨链流程。
- Appendix can support: 环境兼容性、额外阈值组合、故障恢复、codec/dlog 敏感性。
- Experiments intentionally cut: 与论文无关的新模型、新数据集和新隐私机制。

## Experiment Blocks

### Block 1: 加密聚合正确性
- Claim tested: C1
- Dataset / task: 合成小向量；随后随机模型参数块。
- Compared systems: 明文整数 oracle、tMCFE 完整路径。
- Metrics: exact element equality、拒绝率、round-trip time。
- Success criterion: 合法设置逐元素完全相等；所有非法设置确定性失败。
- Priority: MUST-RUN

### Block 2: 主模型质量
- Claim tested: C1
- Dataset / split / task: MNIST/CNN/30 rounds；CIFAR-10/MicroNet/100 rounds；5 clients、3 aggregators。
- Compared systems: plain FedAvg、CrosFed crypto-sim；必要时论文的 HybridAlpha/PrivLDFL adapter。
- Metrics: test accuracy/loss per round，最终值，3 seeds 均值/标准差。
- Success criterion: crypto 与量化明文路径曲线等价；最终指标达到与论文可解释的容差。
- Priority: MUST-RUN

### Block 3: 阈值与攻击负向测试
- Claim tested: C2
- Compared systems: `t`、`t-1`、跨轮、重复 signer、篡改 numerator、错误 `Y`。
- Metrics: 成功/拒绝、错误类型、是否产生 plaintext。
- Success criterion: 仅满足 round context 与阈值的合法集合可恢复。
- Priority: MUST-RUN

### Block 4: 扩展性与开销
- Claim tested: C1, anti-claim
- Setup: client sweep 2/4/6/8/10（s=3）；aggregator sweep 1/2/3/4/5（n=5）；MNIST 30 rounds，CIFAR-10 100 rounds。
- Metrics: phase-exact client/aggregator time、logical/wire/on-chain bytes、peak memory；accuracy/loss。
- Success criterion: 定性斜率与论文一致，并可解释绝对值差异。
- Priority: MUST-RUN

### Block 5: ChainMaker 和合约
- Claim tested: C2, anti-claim
- Setup: institution chains、aggregator chains、relay；四个操作。
- Metrics: transaction/execution gas、latency、receipt、payload bytes。
- Success criterion: 四流程端到端成功，篡改请求失败；inline 与 content-addressed 口径分开。
- Priority: MUST-RUN

## Run Order and Milestones

| Milestone | Goal | Runs | Decision Gate | Cost | Risk |
|---|---|---|---|---|---|
| M0 | 小向量与 schema sanity | known-answer + 负向测试 | exact equality | CPU 小时级 | 公式歧义 |
| M1 | 明文 FL baseline | MNIST quick/full，CIFAR quick | 模型参数量和收敛正常 | GPU 1–3 h | 超参数缺失 |
| M2 | 完整 crypto-FL | 单 batch → 1 round → MNIST full | 与 oracle 等价 | CPU/GPU 2–8 h | Charm 吞吐/dlog |
| M3 | 主结果与 sweep | B2/B4 | 数据齐全且趋势可解释 | 受密码学 CPU 主导 | 总耗时高 |
| M4 | ChainMaker | B5 | receipts 与 gas 可复核 | CPU 小时级 | 大 payload 限制 |

## Compute and Data Budget

- GPU：单卡 RTX PRO 6000；FL 训练串行调度，遵守 `MAX_PARALLEL_RUNS=1`。
- 初始预算：先做不超过 2 小时 pilot；完整阶段总 GPU 不超过 8 小时。
- 最大瓶颈：逐参数椭圆曲线运算和 bounded dlog，预计主要是 CPU 而非 GPU。
- 数据：MNIST/CIFAR-10，下载后记录 checksum 与 split manifest。

## Final Checklist

- [x] Main paper tables are covered
- [x] Novelty is isolated
- [x] Simplicity is defended
- [x] Frontier contribution is explicitly not applicable
- [x] Nice-to-have runs are separated from must-run runs

