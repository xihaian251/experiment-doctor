# Experiment Doctor v1.0 设计规格书

- 状态：设计草案（第一阶段交付物，未编码）
- 基线：Experiment Doctor 0.1.0（已发布并冻结：tag `v0.1.0` → `7c9e550`，PyPI `experiment-doctor==0.1.0`）
- 约束：本文档不修改 v0.1 任何已发布代码；所有设计决策标注 v0.1 实际证据来源
- 证据索引：`phase0-gmmvi/EXPERIMENT_DOCTOR_PHASE0_REPORT.md`（下称 P0）、`acceptance1-torchssl/EXPERIMENT_DOCTOR_ACCEPTANCE1_TORCHSSL.md`（A1）、`acceptance2-crda/EXPERIMENT_DOCTOR_ACCEPTANCE2_CRDA.md`（A2）、`v0.1/docs/rules/`、`v0.1/src/experiment_doctor/schema.py`、`release/0.1.0/` 两份报告

---

## 1. v0.1 经验总结

### 1.1 v0.1 解决了什么问题

v0.1 证明了一件事：**对已发表的 ML 实验 artifacts，可以机械化地重建 project → family → run → metric → aggregation 的 provenance 链，并对"发表的 mean ± spread 是否由它声称的 run 算出来"给出有证据等级的判定**。三个异构真实项目、共约 5,000+ run 的审计（GMMVI 3,483 runs / 205 families / 219 aggregations；TorchSSL 6 run 深审 + 46/46 结构验收；CRDA 1,350 runs / 270 aggregations）确立了三项方法论资产：

1. **证据分级**：每个字段携带 `CONFIRMED / SUPPORTED / INFERRED / UNKNOWN / CONFLICTING` 等级与 source（`path:key:line`），UNKNOWN 不携带值、缺失永不升格为矛盾。
2. **五值规则语义**：ED001–ED010 输出 `PASS / FAIL / INCONCLUSIVE / NOT_APPLICABLE / NOT_RUN`，INCONCLUSIVE ≠ FAIL，无综合信任分，无 SAFE/INVALID 判决。CRDA generic 盲扫描 0 PASS / 0 FAIL / 2185 INCONCLUSIVE——工具在陌生项目上保持沉默而非编造（A2 §40 A–J 十项 false-inference 全零）。
3. **语义审计能力**：能抓到"数字对但语义错"的整类问题——CRDA 的 ED007 PASS×270 与 ED008 FAIL×270 并存（数值可重算、但 `±` 的实现是 population std 而项目文字声称 SEM，40/40 单元格票决一致）；TorchSSL 的 published cell 若按 prose 的"standard errors"解释则全部对不上，按实际代码（`np.std`, ddof=0, 无 ÷√N）解释则 MATCH（A1 §15–16）。

### 1.2 哪些问题无法事后恢复

这是 v1.0 的立论基础。v0.1 的三项目审计给出了一个负存在性证明：**下列信息在实验结束后没有任何已知方法能从归档 artifacts 可靠恢复**，无论审计器多聪明：

| # | 丢失的信息 | 项目证据 | 为什么后验失败 |
|---|---|---|---|
| 1 | seed（3,483/3,483 UNKNOWN） | GMMVI：0 个归档 config 含 seed 键；seed 在外部包 `gmmvi==1.0` 内按 `start_seed+rep` 推导，只打印到已丢失的 stdout（P0 §8） | 派生值不落盘就随进程消失；同 family 的 10 个 run 共享同一 config，seed 是唯一方差来源，却是最先蒸发的事实 |
| 2 | code commit（0/7,004 文件命中） | GMMVI token 扫描零命中 SHA/version/cuda/job_id（P0 §15/§24）；CRDA 1,350 run 的 ED003 全部 INCONCLUSIVE（A2） | HEAD 是时间的函数，归档不携带它；**TorchSSL 提供了正面反证**：logs 打印 `use_azure=False`，而 clone 中 0 个文件含此符号；shipped YAML 的 `dist_url=10006` ≠ logged `10031`——"用今天的 checkout 解释昨天的 run"在该项目上是可证伪的错误（A1 §19–20） |
| 3 | runtime environment | CRDA `runtime_environment is None` ×1350，`requirements.txt` 只是声明（ED010：声明永远不能证明运行时，A2 §15）；TorchSSL log.txt 无任何 python/torch/CUDA 版本串，仅 `device='cuda:0'` ×378 | 进程内解析到的版本、driver、实际 GPU 只在运行时存在 |
| 4 | aggregation membership | GMMVI 成员资格唯一编码是文件名后缀 `.csv` vs `.csv.bad`；`.bad` 把 20 个 outlier 与 2 个 OOM 截断混在一起；被排除的 TALOS/sepyfux index 2（428 行、z=0.56、跑满 86,248 s）在 artifact 层面与 included run **零可区分信号**；run-id→文件映射依赖不可验证的 W&B API 返回顺序（P0 §11–12） | 排除是决策，不是物理事件；不做记录就只剩事后猜测（v0.1 只能给 INFERRED 上限） |
| 5 | 有效计算预算 | GMMVI 真实 wall-time 上限被 sed 注入 gitignored 的 `evaluations/tmp/`；38/98 family 多数 run 在时限 2% 内结束——"final ELBO"实为"deadline ELBO"（P0 §16） | 生效值从未进入任何被归档的文件 |
| 6 | 指标历史完整性 | GMMVI 的 MMD 列被后续一次 `logregacc` 抓取覆盖（BC/GC/BCMB/GCMB 四分支），从归档不可重产（P0 §24） | 覆盖写抹掉旧观测，无版本化 |
| 7 | declared vs actual repetitions | GMMVI 表注称"ten different seeds"，重算 N 实为 5,7,8,4,4,30；TorchSSL README 称 seeds 0,1,2 而 shipped 生成器代码 `seeds=[0]`（P0 §21.5；A1 §4） | 声明与实现的矛盾只能靠双方都在场时暴露——事后单一来源无法裁决 |

另有两类"事后勉强可行但脆弱"的：metric 方向语义（GMMVI `elbo_fb:` 需取负，naive 规则误分类 25/107 family，v0.1 靠逐行读码才 CONFIRMED）；published cell 比对（v0.1 依赖人工转写 `--reported-table`，被明确登记为最薄弱环节，A1 §28.3）。

### 1.3 哪些 provenance 字段必须运行时捕获

把 1.2 一般化，字段按"随什么消失"分三类，**这三类必须 capture-time，其余可保留后验路径**：

- **(a) 随进程消失**：派生 seed、stdout、有效 env vars、解析后的库版本、GPU/driver、心跳、终止原因（OOM-killer 信号、SLURM 信号、异常尾）、有效预算。
- **(b) 随时间漂移**：git commit + dirty 状态、依赖解析结果、数据集文件内容、config 的 effective 值（声明文档 ≠ 生效值，GMMVI 归档 config 恒为声明 doc 的子集）。
- **(c) 是决策而非事件**：哪些 run 进入哪个 published cell、按什么规则（成员资格、排除理由、best/last 选择、聚合公式）。

可以事后：论文表格数值（外部输入）、代码语义方向（读码推断，上限 INFERRED）。

---

## 2. v1.0 核心理念

**Experiment Doctor 不再是 `audit existing experiments`，而是 `capture → track → verify → audit`。**

| 阶段 | 时机 | 动作 | v0.1 对应缺口 |
|---|---|---|---|
| capture | 事前 + 运行中 | `experiment-doctor run` 包装执行：启动瞬间写不可变 lock，运行中追加事件与指标观测 | 1.2 全部 7 项 |
| track | 持续 | append-only 本地 run 目录（`runs/<run_id>/`），无服务器、无数据库 | — |
| verify | 事后即刻 | lock 与 artifacts 自洽重算：commit 是否存在、config/dataset hash 是否漂移、聚合是否复算一致 | TorchSSL "HEAD≠运行码"类错误在提交前被暴露 |
| audit | 事后任意 | **复用 v0.1 的 ED001–ED010 引擎**，对 captured run 与 legacy 项目一视同仁 | — |

时间轴三层：**run 前**（lock：代码/数据/环境/配置/seed 计划）、**run 中**（事件：start/heartbeat/终止因/每条 metric 观测带 step）、**run 后**（聚合声明：哪些 run 进哪个 cell、按什么公式——把 CRDA/TorchSSL 证明过的"prose 与公式不一致"整类错误变成可机检的数据比对）。

继承 v0.1 的不变式（不因升级而放弃）：
1. 缺失 = UNKNOWN，永不推断填补；
2. 无综合信任分、无 SAFE/INVALID/RISKY 判决；
3. audit/verify 只读；capture 只写自己的 `runs/` 目录；
4. 每个字段带证据等级与 source——但对 captured run，source 从"考古反推"变成"运行时一手记录"，等级上限从 INFERRED 提升为 CONFIRMED 的路径第一次存在。

v1.0 的定位一句话：**把 v0.1 证明"事后不可恢复"的东西，变成"事前一行命令就有的"。**

---

## 3. 新核心对象设计：ExperimentRun v1

保留 v0.1 已被证明必要的身份分离：**run_id ≠ seed ≠ repetition_index ≠ family_id**。GMMVI 案例是它的存在理由：同 family 的 10 个 run 只差 seed，成员资格按 result slot（`.csv` 后缀）而非 seed 编码，`result_slot_index` 与 `seed` 一旦混同，"5 个被排除"这类事实就无法表达。

结构（Runtime Capture Layer 包裹 v0.1 字段，而非替换）：

```
ExperimentRun v1
├── Identity      ├─ Dataset       ├─ Code          ├─ Configuration
├── Randomness    ├─ Environment   ├─ Execution     ├─ Artifacts
├── Metrics       ├─ Aggregation   └─ Provenance（每字段 grade+source，v0.1 机制不变）
```

逐字段：为什么需要 / v0.1 证据 / 是否必须运行时捕获 / 缺失时状态。

### Identity
| 字段 | 为什么 | v0.1 证据 | 运行时? | 缺失状态 |
|---|---|---|---|---|
| `run_id`（capture 层生成 ULID） | 全局唯一锚点，其余一切挂在它下面 | GMMVI run id→文件映射依赖 W&B 返回顺序，不可验证（P0 §12） | 是 | UNKNOWN |
| `family_id` = hash(method, task, dataset, config_hash, protocol) | 身份由声明推导而非目录名 | TorchSSL family key 需从 main.py 反推（A1）；GMMVI eval 与 hyperopt 共享 group 名（cw2 多文档） | 是 | 退化为 v0.1 路径 |
| `repetition_index` / `result_slot_index` | 重复槽位 ≠ 种子（见上） | GMMVI `.csv.bad` 按槽位排除 | 是 | UNKNOWN |
| `tracker_run_id` | 外部系统对账用，可选 | GMMVI 仅 22 个被排除 run 的 W&B id 以字面量幸存 | 否 | 允许 UNKNOWN |

### Code
| 字段 | 为什么 | v0.1 证据 | 运行时? | 缺失状态 |
|---|---|---|---|---|
| `git_commit` + `git_dirty` + `diff_hash` | 三态而非单值：clean commit、dirty 工作树、detached | GMMVI 0/7,004；CRDA ED003 全 INCONCLUSIVE；TorchSSL 证明 HEAD≠运行码 | **必须** | ED003 INCONCLUSIVE |
| `entrypoint` + `argv` | 命令是 family/protocol 的一部分 | GMMVI 预算经 sed 注入命令链（P0 §16） | **必须** | UNKNOWN |
| `lock_hash` | 把 run 绑定到本次 lock | — | 是 | — |

### Dataset
| 字段 | 为什么 | v0.1 证据 | 运行时? | 缺失状态 |
|---|---|---|---|---|
| `name` / `version` / `split_hash` | 数据是实验身份一部分 | GMMVI 无 dataset checksum；CRDA 数据集仅目录名 | 指纹**必须**（数据会被更新） | ED001 降级 |
| `preprocessing_hash` | 同数据不同预处理 | GMMVI 21 family 在 live 与 previous_evaluations 文档间歧义（P0 §14） | 是 | UNKNOWN |

### Configuration
| 字段 | 为什么 | v0.1 证据 | 运行时? | 缺失状态 |
|---|---|---|---|---|
| `declared_config`（路径+hash） | 声明面 | GMMVI 归档 config 恒为声明 doc 子集；7/107 hyperopt→eval 链断 | 是 | ED004 |
| `effective_config`（运行时完整 dump） | 生效面，与声明面**分开** | cw2 DEFAULT+per-env 多文档解析是 v0.1 adapter 最重工作量之一 | **必须** | ED004 INCONCLUSIVE |
| `unrecorded_effective_parameters` | 显式列出"只存在于代码默认值"的参数 | GMMVI seed 正是这样消失的 | **必须** | 登记 PROVENANCE_GAP |

### Randomness
`seed`、`seed_derivation`（公式而非只有值）、`determinism_flags`（cudnn.benchmark 等）。证据：GMMVI `start_seed+rep` 只进 stdout（1.2#1）；TorchSSL seed CONFIRMED 6/6 恰证明"落盘的 Arguments dump"就是 capture 该长什么样——v1.0 把它标准化。缺失 → ED002 ALL_SEEDS_UNKNOWN。

### Environment
`runtime_environment`（python/torch/cuda/GPU/driver/hostname/job id）与 `declared_environment`（lockfile hash、env 文件）**保持两个字段**。CRDA 证明分离是本质而非风格：声明永远存在、运行时永远缺席（ED010 INCONCLUSIVE×1350）。缺失 → ED010 INCONCLUSIVE（v0.1 语义不变）。

### Execution
`start/end`、`heartbeat[]`、`exit_code`、`termination_cause`（枚举+一手证据：OOM-killer 行、SLURM 信号、异常尾）、`compute_budget`（**生效值**及其来源）。证据：GMMVI 预算在 gitignored 文件（1.2#5）、`.bad` 混淆 outlier 与 OOM（1.2#4）、ED009 在三项目全部无法 CONFIRM。缺失 → ED009 INCONCLUSIVE。

### Artifacts
`files[] = {path, sha256, role}` 清单（引用不复制）。证据：GMMVI MMD 列被覆盖（1.2#6）——哈希清单使覆盖可检测。run 结束时写。

### Metrics
每条观测 = `(name, value, step, split, timestamp, role ∈ {trajectory, final, best})`，外加 run 级声明：`direction`（larger/smaller_is_better，运行时声明）与 `selection_policy`（BEST/LAST/SPECIFIC_STEP——"发表的数代表哪条观测"）。证据：GMMVI published = last row 且 `elbo_fb:` 需取负（naive 规则误分类 25/107）；TorchSSL best−last 每 run 0.16–0.32 pts、family 均值差 ≈0.23 > published spread 0.05——**选错观测的偏移量大于声称的不确定度**（A1 §14）。ED005 由此从"反推声明"升级为"核对声明与数据一致"。缺失 → ED005 UNKNOWN。

### Aggregation
run 后由聚合脚本产出一等记录（不是 prose）：`members[]`、`inclusion_rule`、`statistic`、`spread_formula`（符号+ddof+是否 ÷√N+舍入）、`reported_cell` 绑定。证据：CRDA prose-SEM vs 实现-population-std（ED008 FAIL×270）；TorchSSL `average_log.py:132` 与 README 矛盾；GMMVI 表注 N=10 vs 实际 5,7,8,4,4,30；v0.1 全部依赖外部人工转写 reported_table（最薄弱环节）。缺失 → 回退 v0.1 反推路径（INFERRED 上限）。

### Provenance
v0.1 的 `(grade, source)` 机制原样保留。区别：captured run 的 source 指向 lock/manifest 一手记录；legacy run 仍走 adapter 考古。两条路径共用同一 schema——**v0.1 审计引擎零修改即可审计 v1.0 产物**，这是向后兼容的硬约束。

---

## 4. Experiment Lock 文件设计：`experiment.lock.json`

类比 package-lock.json：package-lock 锁定"代码的依赖闭包"，experiment.lock 锁定"实验的身份闭包"——代码、数据、配置、随机性、环境、预算六个漂移源的同一时刻快照。

```json
{
  "schema_version": "1.0",
  "run_id": "01J...", "created_at": "...",
  "code":    {"git_url": "...", "commit": "...", "dirty": true, "diff_hash": "sha256:...",
               "entrypoint": "train.py", "argv": ["..."]},
  "dataset": {"name": "...", "version": "...", "fingerprint": "sha256:...", "split_hash": "..."},
  "config":  {"declared_hash": "...", "effective_file": "run://effective_config.json"},
  "randomness": {"seed": 42, "seed_derivation": "cli --seed", "determinism_flags": {...}},
  "environment": {"python": "3.11.9", "torch": "2.4.0+cu121", "cuda_driver": "...",
                   "gpus": [{"name": "...", "memory": "..."}], "hostname": "...",
                   "job_id": "...", "packages_hash": "...", "env_vars_allowlist": {...}},
  "budget":  {"wall_time_limit_s": 86400, "max_iters": 1048000, "source": "effective"},
  "execution": {"started_at": "...", "ended_at": "...", "exit_code": 0,
                 "termination_cause": "ITERATION_CAP", "heartbeat": [...]},
  "metrics_manifest": [{"name": "-elbo", "file": "run.csv", "role": "trajectory",
                         "direction": "larger_is_better", "selection": "last"}],
  "aggregation_plan": {"family_id": "...", "repetition_index": 3},
  "lock_hash": "sha256:<self, computed over all above>"
}
```

设计决策与理由：

1. **启动瞬间写、之后只 append**。`execution` 之外不可变；终止块由 wrapper 在子进程退出时补写并记录原因。lock 的自哈希使篡改/漂移可检测（verify 重算）。
2. **dirty 树记 `diff_hash` 而非拒绝运行**。科研现实是代码一直在动（TorchSSL/CRDA 全部在移动的代码上跑）；工具应记录现实而非假装它不存在。`dirty=true` 时 audit 侧对应字段最高 SUPPORTED，不给 CONFIRMED——诚实分级。
3. **`budget.source: "effective"` 是字段而非脚注**。GMMVI 证明"生效预算"和"声明预算"可以隔着一个 gitignored 文件。
4. **数据集存指纹不存副本**。哈希足以事后验证"是不是同一份数据"，复制数据越出只读边界。
5. **为什么这些信息无法可靠后验恢复**：见 §1.2 表——每一个 lock 字段都对应一个已发生的、三项目中实测 100% 丢失（GMMVI commit：0/7,004 命中）或可证伪（TorchSSL `use_azure`）的恢复失败案例。一般化论证：provenance 字段是时间的函数，事后审计只能在 t_now 采样，而实验结论属于 t_run；lock 是唯一被安排进实验生命周期的采样点。

---

## 5. CLI 设计

```bash
experiment-doctor init                      # 项目根写 ed.toml（捕获策略：env var 白名单、指标声明、数据路径）
experiment-doctor run python train.py --seed 3   # 采 lock → spawn 子进程（stdio 透传，捕获 stderr 尾部/信号/exit code）→ 落 runs/<run_id>/
experiment-doctor verify [<run_id>|--all]   # lock vs 现存 artifacts 自洽重算（commit 存在性、config/dataset hash 漂移、metrics 文件哈希、聚合声明复算）
experiment-doctor audit [--reported-table published_cells.json]   # v0.1 完整 ED001–ED010 引擎
experiment-doctor report                    # report.json / report.md（v0.1 格式不变）
```

兼容命令 `scan / rules / adapters` 原样保留。

约束：
- `run` 是 wrapper，不是调度器：不排队、不重试、不管 GPU 分配、不做 daemon。
- `verify` 输出复用 RuleStatus 五值，不发明第二套状态词汇；verify ≠ audit（前者查"lock 与现场是否同一事实"，后者查"发表与证据是否一致"）。
- 指标捕获零强制侵入：MVP 不要求装 SDK。三个来源按优先级：(1) 解析 run 目录内既有 CSV/JSON 日志（复用 v0.1 adapter 解析逻辑）；(2) `--metrics-glob` 声明式抓取；(3) 可选单函数 `ed.log(name, value, step)`（一个文件、无框架依赖，仅当用户想要 role/step 精确性时）。
- 无 GUI；报告仍是 JSON/Markdown。

---

## 6. Framework Integration

原则：集成只有两种合法形态——**capture（框架无关的 wrapper）**与**read-only reader（把既有生态的落盘格式翻译成 ExperimentRun v1）**。不做 instrumentation-heavy 的深钩子（v0.1 教训：adapter 模式证明"只读反推 + 显式 gap 登记"足以处理异构生态，而钩子意味着跟随每个上游版本）。

| 生态 | 形态 | 理由与边界 |
|---|---|---|
| **PyTorch** | capture 层内省（`torch.version.*`、device、cudnn flags 写入 lock 的 environment 块） | 唯一"直接支持"项，因为 wrapper 已在子进程旁，读一次版本零成本。不做 monkeypatch、不 hook 训练循环 |
| **Hydra** | read-only reader（优先） | `.hydra/{config.yaml, overrides.yaml, log.txt, cfg.job_launch}` 几乎是天然 lock：resolved config + overrides + 命令都在。reader 把 outputs/<dir>/ 映射为 ExperimentRun。不 hook launcher/sweeper |
| **PyTorch Lightning** | read-only（`lightning_logs/`、CSVLogger、best checkpoint 选择线） | 不做 Callback（逼用户改代码 = 违背零侵入）。best/last 语义交给 ED005 |
| **Weights & Biases** | read-only 本地导出（offline-run 目录、`wandb-files` 导出） | **绝不做网络调用**。GMMVI 证明 W&B API 返回顺序不可验证——v0.1 里它只是 INFERRED 上限的来源，v1.0 不把它升级为依赖 |
| **MLflow** | read-only（`mlruns/` 本地文件布局：meta.yaml、tags、metrics） | MLflow 本身是 capture 系统；v1.0 对它的定位是**审计者而非竞争者**：ED005–ED008 完全可以跑在 MLflow 记录的 run 与聚合上，且 v0.1 已证明这类聚合普遍有语义问题 |

MVP 只带 Hydra + MLflow 两个 reader（磁盘格式稳定、覆盖面大、纯文件解析），Lightning/W&B 放 v1.1。

---

## 7. v1.0 MVP 范围冻结（3 个月可完成）

**只做**：
1. `run` wrapper + `experiment.lock.json`（§4 七块）+ append-only `runs/<run_id>/` 布局；
2. `verify`：lock 自洽（哈希、commit 存在性、config/dataset 漂移）+ 聚合声明复算（扩展 v0.1 聚合引擎接受 declared-membership 输入，替代人工转写）；
3. `audit`/`report`：v0.1 引擎原样复用，**不加新规则**；报告新增 capture coverage 元数据（各字段 grade 分布计数——是统计不是分数）；
4. Hydra + MLflow 两个 read-only reader；
5. 可选 `ed.log` 单函数。

**明确不做**：GUI、Agent/多智能体、自动调参、自动修改代码、云平台/远程服务、数据库/telemetry/server、W&B/Lightning/TensorBoard 解析、ED011+ 新规则、非 Python 语言、复现基准跑分。

**MVP 验收门（设计即测试计划）**：
- 正向：自建 synthetic PyTorch mini 项目，3 seeds × 1 family → lock 完整 → `verify` 全绿 → `audit` 下 ED002/ED003/ED004/ED009/ED010 首次基于一手记录给出 PASS（而非三项目中永远 INCONCLUSIVE）——这是"capture 有效"的最小可证伪命题；
- 负向：篡改 lock（改 commit/seed/config hash 各一）→ verify 必须逐项检出不漏；删除一个成员 run → 聚合声明复算必须 MISMATCH；
- 回归：v0.1 的 118 个测试与三项目验收证据（21/21、46/46、25/25、19/19）在 audit 引擎上保持全部成立——v1.0 不得使任何既有审计结论漂移。

---

## 8. 与论文/研究价值分析

**不新的东西先说清**：实验追踪本身不新（MLflow、W&B、Sacred、DesignFlow），捕获环境指纹也不新（reprozip/RELF、runq）。v1.0 不能声称"解决可复现性"。

**v0.1 已经产出、且文献中稀缺的实证结果**（论文的真正地基）：
1. **事后 provenance 恢复上限的大规模实证**：三个异构公开项目、5,000+ run 的字段级恢复率表——commit 0/3,483（GMMVI）与 0/1,350（CRDA）、seed 0/3,483、membership 唯一编码是文件后缀、表注 N=10 vs 实际 {5,7,8,4,4,30}、best−last 偏移(≈0.23) > published spread(0.05)。这与 Pineau/Kapoor 的 NeurIPS 可复现性挑战同族，但粒度到字段、方法带证据分级，且含正面反证（TorchSSL 的 `use_azure` 案例直接证伪"clone 可解释归档"）。
2. **一类现有系统检不出来的错误**：tracker 忠实记录数字，从不检查"±"是不是 prose 声称的那个量（CRDA SEM-vs-population-std、TorchSSL "standard errors"-vs-无÷√N），也从不检查发表的数代表 best 还是 last。"语义审计"（声明文本 × 实现代码 × 归档数值三方对账）是可辩护的新颖点。
3. **设计模式贡献**：五值规则 + 证据分级 + UNKNOWN 纪律（INCONCLUSIVE ≠ FAIL）作为可信审计的接口约定——CRDA 盲扫描 2185 INCONCLUSIVE / 0 虚假判决是它的行为证明。

**诚实的论文形态排序**：(a) NeurIPS D&B / MLSys 工具+资源论文：v0.1 审计引擎 + 三项目实证 + v1.0 capture 闭环；(b) 纯分析论文："What Can Post-hoc Provenance Recovery Actually Recover?"——数据现在就有；(c) **不可声称**：生态影响、被他人采用、"guarantees reproducibility"（v0.1 README 的禁令延续）。

**前置条件**：v1.0 必须至少在一个新项目上演示 capture-first 使 ED001–ED010 的主体从 INCONCLUSIVE 升为基于一手记录的 PASS，否则论文只支撑审计半边（那仍是有价值的 (b) 型论文）。

---

## 9. 技术路线图

### v1.0 MVP（3 个月）
- **目标**：单机 capture → verify → audit 闭环；"事后不可恢复"清单（§1.2）逐项变成"运行时自动有"。
- **功能**：§7 的 5 项。
- **不做**：服务器、深 instrumentation、新规则、GUI、云。

### v1.1（+3 个月）
- **目标**：把聚合侧的最后一处人工转写消掉；批量实验的 lock 经济学。
- **功能**：`ed.aggregate` 命令产出聚合声明（members/公式/舍入成为一等数据，ED006–ED008 不再依赖外部 reported_table）；family 级 lock 复用（多 seed 批跑共享身份、逐 run 只记 diff）；Lightning + W&B-本地导出 reader；跨项目 verify（拿别人 release 的 lock 在自己的 checkout 上验证）；ED011+ 候选规则评估（仅当 capture 产生了 v0.1 五规则覆盖不了的新证据类型）。
- **不做**：团队协作服务器、自动修复。

### v2.0（6–12 个月，依赖 v1.x 真实采用）
- **目标**：从单机工具到可转让的证据。
- **功能**：可分享 evidence bundle（lock + manifest + report 的签名包），第三方可离线 `verify`；论文-仓库绑定工作流（camera-ready 表格单元 → run 集合的机器可读链接）；CI 门禁形态（verify 作为 PR check）；社区规则 registry。
- **不做**：全自动科学判断、misconduct 检测（v0.1 边界永久保留）。

### 与 v0.1 的关系（硬约束）
v0.1 = 0.1.0 已发布冻结，不改一行。v1.0 在新目录/新包版本线开发；audit 引擎以依赖方式复用而非 fork；schema 演进保持 `ExperimentRun v1` 能无损序列化 v0.1 全部字段（v0.1 的 report round-trip 测试是兼容性地基）。

---

## 附：本设计中每个决策的证据锚点速查

| 设计决策 | 锚点 |
|---|---|
| lock 必须运行时写 | P0 §8/§15（seed、commit 全灭）；A1 §19–20（HEAD≠运行码的正面反证） |
| dirty+diff_hash 而非拒绝 | A2（CRDA/TorchSSL 均在移动代码上跑） |
| runtime vs declared environment 双字段 | A2 §15（ED010 INCONCLUSIVE×1350 由混同造成） |
| 有效预算入 lock | P0 §16（sed 注入 gitignored，38/98 family deadline-truncated） |
| metric role + selection_policy | A1 §14（best−last 0.16–0.32 > spread 0.05）；P0（last-row published、符号取负） |
| 聚合声明一等化 | A2 §15（ED008 FAIL×270）；A1 §15–16（prose-vs-formula）；P0 §21.5（N 漂移） |
| membership+reason 运行时记录 | P0 §11–12（.bad 混淆、零信号排除 run、API 顺序不可验证） |
| 保留 UNKNOWN 纪律与五值规则 | v0.1 全部三项目验收（19/19、25/25、0/10 forbidden inference） |
| reader-only 生态策略 | v0.1 四 adapter 全部以只读反推成功交付 |
