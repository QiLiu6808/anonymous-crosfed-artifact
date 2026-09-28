# CrosFed 代码结构

本文档描述仓库整理后的稳定分层。目标是让算法实现、实验应用、外部系统适配和命令行入口彼此独立，同时保留旧的 `scripts/*.py` 调用方式。

## 目录

```text
CrosFed/
├── src/crosfed/                 # 可安装的 Python 包
│   ├── domain/                  # 消息、轮次上下文、状态机；无框架依赖
│   ├── crypto/                  # 定点编码、签名、tMCFE
│   ├── ml/                      # 模型、训练、FedAvg、参数序列化、数据校验
│   ├── ledger/                  # LedgerPort/RelayPort 与内存、ChainMaker 客户端
│   ├── orchestration/           # 单轮安全聚合工作流
│   ├── baselines/               # 明确标注的 clean-room 基线适配器
│   ├── metrics/                 # 事件和阶段计时
│   ├── experiments/             # 训练、扫描、安全实验、结果汇总应用
│   ├── integrations/chainmaker/ # CMC 桥、配置、基准和端到端流程
│   └── cli/                     # 很薄的命令行适配层
├── configs/                     # 只保存声明式实验配置
│   ├── paper/                   # 论文主实验
│   ├── baselines/               # 基线实验
│   ├── scalability/             # 客户端/聚合器扫描
│   ├── repetitions/             # 多随机种子矩阵
│   ├── calibration/             # 模型候选校准
│   └── chainmaker/              # ChainMaker 实验选择
├── contracts/                   # Solidity 合约；构建产物不入库
├── chainmaker/config/           # ChainMaker 部署模板
├── scripts/                     # 兼容包装器和 shell 运维脚本
├── tests/                       # 单元与轻量集成测试
├── docs/                        # 架构、忠实度和实现状态
└── runs/                        # 本地生成的实验产物；不纳入匿名源码仓库
```

## 依赖方向

```text
domain ← crypto / ml / ledger / metrics
                 ↓
            orchestration
                 ↓
             experiments
                 ↓
                 cli

ledger ← integrations/chainmaker
```

约束如下：

- `domain` 不依赖 PyTorch、Charm 或 ChainMaker。
- `orchestration` 只面向 `LedgerPort` 和 `RelayPort`，不包含 CMC 命令细节。
- `integrations` 可以依赖核心端口，核心算法不能反向依赖部署脚本。
- `experiments` 负责配置解析、训练生命周期和机器可读产物。
- `cli` 只暴露入口；可复用函数应放在 `experiments` 或 `integrations`。
- `scripts/*.py` 仅用于兼容匿名仓库中已经公布的命令，不再承载业务逻辑。

## 标准入口

安装后推荐使用：

```bash
crosfed-train --config CONFIG --output RUN/result.json
crosfed-sweep --sweep SWEEP --output-root runs --dry-run
crosfed-security --output runs/R020_adversarial_sanity/result.json
crosfed-summarize --results "runs/**/result.json" --output-prefix runs/summary/paper
crosfed-chainmaker-config --help
crosfed-chainmaker-e2e --help
crosfed-contract-bench --help
```

也可以使用 `python -m crosfed.cli.train`。旧命令 `python scripts/run_federated.py` 保持兼容并调用同一实现。

## 实验产物约定

每个训练运行使用独立目录：

```text
runs/<run_id>/
├── resolved_config.yaml
├── environment.json
├── split_manifest.json
├── events.jsonl
├── round_metrics.csv
├── checkpoint.pt
└── result.json
```

`result.json` 是完成状态与论文指标的主入口；原始事件、数据摘要和配置快照用于审计，不应由汇总脚本猜测或覆盖。

## 修改位置速查

| 需求 | 修改位置 |
|---|---|
| 修改 tMCFE 数学实现 | `src/crosfed/crypto/tmcfe.py` |
| 修改量化策略 | `src/crosfed/crypto/codec.py` |
| 修改模型或本地训练 | `src/crosfed/ml/federated.py` |
| 修改安全聚合流程 | `src/crosfed/orchestration/secure_round.py` |
| 新增实验参数组合 | `configs/` 与 `src/crosfed/experiments/sweep.py` |
| 修改结果字段或检查点 | `src/crosfed/experiments/federated.py` |
| 修改 ChainMaker CMC 解析 | `src/crosfed/integrations/chainmaker/bridge.py` |
| 新增命令 | `src/crosfed/cli/` 和 `pyproject.toml` |

## 测试边界

- 核心算法测试不应连接网络或下载数据。
- ChainMaker 工具通过递归解析器和客户端边界做轻量测试；真实链执行单独记录。
- 长时间训练不属于默认 `pytest` 门禁。
- 任何加密聚合运行都必须保留与量化明文 oracle 的精确比较。
