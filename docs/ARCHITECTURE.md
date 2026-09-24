# CrosFed 完整复现：整体架构设计

**状态**：Architecture freeze candidate  
**日期**：2026-09-22  
**依据**：用户提供的论文 LaTeX 正文

## 1. 复现目标与边界

本工程要复现的不是单一训练脚本，而是论文的四条证据链：

1. **模型质量**：5 个机构、3 个聚合器时，MNIST/CIFAR-10 的收敛曲线与最终 accuracy/loss。
2. **密码学正确性**：向量加权 tMCFE 的 `Setup / SKDistribute / DKGenerate / Encrypt / ShareDecrypt / CombineDecrypt`，并验证少于阈值不能恢复、轮次标签不能重放。
3. **扩展性**：客户端数 `n ∈ {2,4,6,8,10}`、聚合器数 `s ∈ {1,2,3,4,5}` 时的时间和字节数趋势。
4. **跨链流程**：四个论文算法对应的上传/下载合约、签名/哈希/轮次校验、relay 路由和 gas 报告。

安全证明本身不通过实验“复现”；代码将复现其可执行前提和负向测试。默认信任模型严格遵照论文：KGC、机构和链诚实，聚合器可恶意，最多 `t-1` 个聚合器串谋。

## 2. 总体分层

架构图见 [`figures/crosfed-system-architecture.md`](../figures/crosfed-system-architecture.md)。工程分为六层：

| 层 | 职责 | 核心约束 |
|---|---|---|
| Domain | 配置、消息 schema、round ID、身份、状态机 | 不依赖 PyTorch/Charm/ChainMaker |
| ML plane | 数据划分、CNN/MicroNet、本地训练、评测、参数展平 | 明文 FedAvg 是密码学路径的 oracle |
| Crypto plane | 定点编码、SS512 群、tMCFE、Lagrange、dlog | 所有边界显式；拒绝溢出和错误轮次 |
| Ledger plane | 签名、交易、机构链/聚合器链、relay | 先内存实现，再替换 ChainMaker，业务接口不变 |
| Orchestration | 初始化与逐轮执行、故障注入、恢复 | 每一步幂等且可 checkpoint |
| Evidence | phase timer、wire bytes、gas、CSV/JSONL、绘图 | 原始测量与论文派生指标同时保存 |

这种拆分允许三种运行模式共用同一训练与密码学实现：

- `plain`：明文 FedAvg，用于收敛基准和 oracle。
- `crypto-sim`：真实 Charm tMCFE + 内存账本/relay，用于主实验和规模实验。
- `chainmaker`：真实 Charm tMCFE + ChainMaker 多链部署，用于四合约与 gas/跨链实验。

## 3. 一轮训练的唯一状态机

```text
ROUND_CREATED
  → LOCAL_TRAINED
  → ENCODED
  → ENCRYPTED
  → LOCAL_UPDATES_COMMITTED
  → COMMITTEE_FROZEN
  → SHARES_COMPUTED
  → SHARES_COMMITTED
  → THRESHOLD_REACHED
  → GLOBAL_DECRYPTED
  → EVALUATED
  → ROUND_FINALIZED
```

任一阶段失败只可从最后一个已验证 checkpoint 继续。`committee_frozen` 必须发生在 `ShareDecrypt` 前，因为论文中的 Lagrange 系数依赖同一个集合 `S`；不同聚合器不能各自选择不同的 `S`。

### 3.1 单轮数据流

1. Orchestrator 发布 `(experiment_id, round_id, model_digest, S, t)`。
2. 每个机构从相同 global checkpoint 开始本地训练，得到扁平向量 `x_i`。
3. `ParameterCodec` 将浮点数转换为有界有符号整数；`Y_i` 编码样本权重。
4. 机构用 `ek_i` 和规范化轮次标签加密，签名后提交机构链。
5. 每个聚合器经 relay 获取并验证本轮全部 `n` 个密文，使用对应 `dk_{j,L,Y,t}` 和冻结的委员会 `S` 计算份额。
6. 聚合器签名份额并提交聚合器链。
7. 机构经 relay 获得至少 `t` 个份额，验证共同 numerator、身份、签名、轮次与委员会。
8. `CombineDecrypt` 恢复整数加权模型，经 dlog 和 codec 解码为 global model。
9. 与明文 oracle 逐元素比较，再评测 accuracy/loss 并进入下一轮。

## 4. 关键接口与数据契约

所有可持久化对象采用版本化 canonical serialization；哈希和签名只覆盖 canonical bytes，禁止直接签 Python pickle。

```python
class SecureAggregator(Protocol):
    def setup(self, spec: CryptoSpec) -> PublicParams: ...
    def issue_client_key(self, client_id: int) -> EncryptionKey: ...
    def issue_round_share_key(self, round_ctx: RoundContext,
                              aggregator_id: int) -> ShareKey: ...
    def encrypt(self, encoded_update: IntVector,
                key: EncryptionKey, round_ctx: RoundContext) -> Ciphertext: ...
    def share_decrypt(self, ciphertexts: list[Ciphertext],
                      key: ShareKey, round_ctx: RoundContext) -> PartialShare: ...
    def combine(self, shares: list[PartialShare],
                round_ctx: RoundContext) -> IntVector: ...

class LedgerPort(Protocol):
    def commit(self, envelope: SignedEnvelope) -> Receipt: ...
    def query_round(self, kind: MessageKind, round_ctx: RoundContext) -> list[SignedEnvelope]: ...

class RelayPort(Protocol):
    def query(self, source_chain: ChainId, target_chain: ChainId,
              request: SignedQuery) -> SignedQueryResponse: ...
```

核心 schema：

| 对象 | 必含字段 |
|---|---|
| `RoundContext` | schema version, experiment ID, round, `n/s/t`, ordered `S`, model digest, codec ID, function/weight digest |
| `EncryptedLocalUpdate` | client ID, round context digest, `ct0`, `ct1`, timestamp, payload digest |
| `PartialGlobalUpdate` | aggregator ID, round context digest, shared numerator, denominator shares, timestamp, payload digest |
| `SignedEnvelope` | message kind, signer ID, canonical payload, signature, transaction hash |
| `MetricEvent` | run ID, phase, actor ID, round, wall/cpu time, logical/wire bytes, peak RSS/GPU memory |

## 5. tMCFE 实现设计

### 5.1 数学核心

严格实现论文六算法，并保留一个小向量参考实现。生产向量实现只能做 chunking/并行，不允许改变数学语义。

- `Setup(λ,n,η)`：生成 SS512 群参数、`W/U/α`。
- `SKDistribute(i)`：生成机构 `ek_i`。
- `DKGenerate(Y,j,L,t,S)`：以 Shamir 多项式生成 round-specific share key。
- `Encrypt(x_i,L,ek_i)`：逐坐标生成 `ct0/ct1`。
- `ShareDecrypt({ct_i},Y,j,S,t)`：计算共同 numerator 和聚合器 `j` 的 denominator share。
- `CombineDecrypt({ct'_j})`：验证共同字段，组合至少 `t` 个合法份额并求有界 dlog。

### 5.2 浮点、负数与 dlog

论文未给出编码细节，这是复现的最高风险点。设计上必须通过 `ParameterCodec` 隔离：

```text
float tensor → deterministic flatten → clip → scale/round → signed int
signed int → exponent modulo p
group element → bounded signed dlog → inverse scale → tensor shapes
```

第一版使用**按张量定点量化**，并记录 `scale/clip/max_abs/saturation_count`。解密界由 `n`、权重分母和最大编码值推导，超界立即失败。dlog 后端提供：

- `LookupTableDLog`：论文同款 `(x,g^x)` 预计算，做性能复现。
- `BabyStepGiantStepDLog`：较大边界的正确性后备。
- `OracleDLog`：仅测试使用，绝不计入论文时间。

### 5.3 必须先锁定的正确性不变量

- 任意小向量：`decrypt(encrypt(x_i),Y) == Σ_i x_i ∘ Y_i`。
- 任取相同 `S` 中任意 `t` 个合法份额，恢复结果一致。
- 少于 `t` 个份额、跨轮份额、重复 signer、非 `S` 成员均拒绝。
- 恶意聚合器改变 `ct'_{j,0}` 时，共同 numerator 一致性检查失败。
- 加密聚合结果与明文定点 oracle 逐元素完全相等，之后才允许跑神经网络。

## 6. ML 复现设计

### 6.1 数据和模型

- MNIST：CNN，目标参数量 **19,518**，30 个 global rounds。
- CIFAR-10：MicroNet，目标参数量 **73,198**，100 个 global rounds。
- 主设置：5 clients、3 aggregators；阈值 `t` 由论文/原始 artifact 补齐，未补齐前作为显式配置，禁止硬猜藏在代码里。
- 数据缓存、下载 checksum、split manifest 全部落盘；每个样本的 client assignment 可重放。

论文没有给出卷积层细节、优化器、本地 epoch、batch size、学习率、数据增强、IID/Non-IID 划分和随机种子。因此模型注册器必须对参数量做 assertion；超参数通过逐项、可审计的小范围校准寻找与曲线相符的组合，不能把论文最终数值写死为输出。

### 6.2 聚合语义

实现两种 `Y` 编码并由实验决定论文实际语义：

- `uniform`：每客户端等权。
- `sample_weighted`：按本地样本数加权。

为了避免有限域除法与定点除法混淆，密码学层先恢复整数加权和与公开分母，再由 codec 做确定性除法。每轮保存明文 FedAvg oracle digest。

## 7. 账本与跨链设计

### 7.1 两阶段后端

`InMemoryLedger + InMemoryRelay` 精确执行四算法的校验逻辑，使 ML/密码学调试不依赖链。通过全部端到端测试后，再提供：

- `ChainMakerInstitutionLedger`
- `ChainMakerAggregatorLedger`
- `ChainMakerRelay`

三者实现同一 ports，不得在 orchestrator 中出现 ChainMaker 特判。

### 7.2 合约边界

四个论文算法映射为两个 registry 合约加两条经过 relay 的 query 路径：

1. `submitEncryptedLocalUpdate`（Algorithm 1）
2. `queryEncryptedLocalUpdates`（Algorithm 2）
3. `submitPartialGlobalUpdate`（Algorithm 3）
4. `queryPartialGlobalUpdates`（Algorithm 4）

合约验证 schema version、注册身份、round、唯一键、payload hash、签名和 timestamp policy。大密文同时支持：

- `inline`：忠实论文语义，用于可承载的小向量/gas 微基准。
- `content_addressed`：链上 digest + 分块对象，用于完整模型端到端。

两类结果必须分开报告，不能把 digest 模式的 gas 冒充论文全文密文上链成本。论文中近 7.75–29.10 MB 的上传量与约 0.9M gas 是否能同时成立，需要专项审计。

## 8. 观测、计时与实验产物

计时采用 `perf_counter_ns`，CUDA 阶段前后同步。每一阶段单独记录：

- client：load/train、flatten、encode、encrypt、serialize、sign、commit。
- aggregator：relay fetch、verify、share decrypt、serialize、sign、commit。
- institution receive：relay fetch、verify、combine/dlog、decode/load state。

同时输出两种口径：`phase_exact`（原始阶段）与 `paper_derived`（按论文定义组合）。通信量同时给 `logical_payload_bytes`、`serialized_wire_bytes`、`on_chain_bytes`，避免 Python 对象大小与网络载荷混淆。

标准运行目录：

```text
runs/<run_id>/
├── resolved_config.yaml
├── environment.json
├── split_manifest.json
├── events.jsonl
├── round_metrics.csv
├── checkpoints/
├── crypto_audit/
├── chain_receipts/
└── figures/
```

## 9. 建议仓库结构

```text
CrosFed/
├── configs/{sanity,paper,scalability,baselines,chainmaker}/
├── src/crosfed/
│   ├── domain/{config,messages,state_machine}.py
│   ├── ml/{data,partition,models,trainer,flatten}.py
│   ├── crypto/{codec,groups,tmcfe,dlog,signatures}.py
│   ├── ledger/{ports,memory,chainmaker,relay}.py
│   ├── orchestration/{kgc,institution,aggregator,runner}.py
│   ├── metrics/{events,profiler,communication}.py
│   └── cli.py
├── contracts/{EncryptedUpdateRegistry,EncryptedUpdateRelay,PartialUpdateRegistry,PartialUpdateRelay}.sol
├── chainmaker/{docker,config,scripts}/
├── src/crosfed/baselines/{hybridalpha,privldfl}.py
├── tests/{unit,integration,security,e2e}/
├── scripts/{run_sweep,make_tables,make_figures}.py
├── figures/
├── docs/
└── runs/
```

## 10. 构建顺序和验收门

| 阶段 | 交付 | 进入下一阶段的硬门槛 |
|---|---|---|
| M0 Contract freeze | schema、配置、state machine、小向量公式测试 | 论文公式歧义均有显式决定或 TODO gate |
| M1 Plain FL | MNIST/CIFAR 数据、精确参数量模型、FedAvg | 单机可复现；checkpoint resume 等价 |
| M2 Crypto core | Charm SS512 tMCFE、codec、dlog | 小向量 known-answer 与负向测试全过 |
| M3 Crypto-FL | 完整参数向量、chunking、内存链 | 每轮与量化明文 oracle 等价；MNIST sanity 收敛 |
| M4 Evidence | 主设置、client/aggregator sweep、基线 | 自动生成论文表图，原始事件可追溯 |
| M5 ChainMaker | 多链、relay、Solidity、gas | 四流程 e2e 全过，交易 receipt 完整 |
| M6 Fidelity audit | 旧环境容器复跑、差异报告 | 明确 exact/close/trend-only 三档结论 |

## 11. 当前风险与处理

| 风险 | 处理 |
|---|---|
| 原论文缺少训练超参数和模型结构 | 参数量 assertion + 曲线校准；所有尝试保留配置 |
| `r_z` 是否应带 client 下标存在记号歧义 | 以正确性方程和小向量 oracle 判定，两种解释做测试 |
| `S` 与阈值 `t` 未在实验段明确给出 | round context 显式化；从 TAPFed/公开 artifact/作者材料补证 |
| dlog 查表可能成为内存或时间瓶颈 | 先推导严格界，再选择 LUT/BSGS；记录预计算是否计时 |
| 完整模型密文极大 | chunked streaming + mmap cache；绝不以 mock 替代主密码学数据 |
| 原环境已过旧且当前 Blackwell 不支持旧 CUDA 栈 | 现代环境主跑；容器仅做 CPU/兼容性核验，报告环境差异 |
| 基线 PrivLDFL 可能无公开代码 | 独立 adapter；先复现算法再做同硬件公平测量，注明非官方实现 |

## 12. 架构冻结结论

代码实现应从 **小向量 tMCFE 正确性** 和 **明文 FL oracle** 两条独立轨道开始，汇合后再接 ChainMaker。这样任何精度、密码学或跨链错误都能被定位在单层，不会在全栈运行中互相掩盖。第一阶段不追求论文的 99.10%/78.32%，而是先证明每轮加密聚合与明文定点聚合严格等价。
