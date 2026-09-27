# Experiment Doctor v1.0 MVP 实施计划

- 状态：实施计划（本文件不编码；执行以本文为准）
- 上游文档：`docs/v1/EXPERIMENT_DOCTOR_V1_DESIGN.md`（设计原则已冻结：audit → capture → track → verify → audit）
- 基线：v0.1.0 已发布并冻结（tag `v0.1.0` → `7c9e550`，PyPI `experiment-doctor==0.1.0`）。本计划**不修改该 release 的任何字节**；v1.0 开发在 GitHub 仓库 `xihaian251/experiment-doctor` 的 `master`（自 `e17ab18` 之后）上以新模块增量进行，v0.1 的 tag/PyPI 制品永不移动、永不重发。
- 证据引用缩写：P0 = Phase 0 GMMVI 报告，A1 = TorchSSL 验收报告，A2 = CRDA 验收报告（路径见设计规格书头部）。

---

## 第一部分：MVP 边界冻结

v1.0 MVP **只做**以下 5 项，多一项即越界：

| # | 功能 | 命令 | 交付物 |
|---|---|---|---|
| 1 | 初始化捕获策略 | `experiment-doctor init` | 项目根 `ed.toml`（捕获策略：数据路径、env-var 白名单、输出目录）；不生成 lock（lock 属于 run 时刻） |
| 2 | 运行时捕获 | `experiment-doctor run -- python train.py` | 启动瞬间采 lock（command / git commit / dirty state / python 与包版本 / 硬件 / seed（尽力，见 §4 randomness）/ 时间戳 / 输出目录），子进程 stdio 透传 + stderr 尾部与信号捕获，退出后补 execution 块；产物落 `runs/<run_id>/` |
| 3 | 完整性验证 | `experiment-doctor verify [<run_id> \| --all]` | lock 自洽 + 四类漂移检测：code drift、config drift、environment drift、dataset fingerprint drift；输出复用 RuleStatus 五值 |
| 4 | 审计兼容 | `experiment-doctor audit` | v0.1 ED001–ED010 引擎**原样**可跑：对 captured 项目与 legacy 项目（4 个 adapter）行为不变 |
| 5 | 证据包 | `experiment-doctor bundle [<run_id>]` | `experiment_bundle/`：`experiment.lock.json` + `manifest.json`（run 与文件的角色索引）+ `hashes.json`（内容寻址清单） |

与设计规格书 §7 的唯一差异（本计划显式裁决）：**Hydra / MLflow read-only reader 移出 MVP**，推迟到 v1.1。理由：MVP 的可证伪命题是"capture-first 让 INCONCLUSIVE 变 PASS"，只需自建 synthetic 项目即可验证；reader 不服务于该命题，且会引入上游格式维护成本。

与 v0.1 的关系不变式（继承设计规格书 §2）：缺失 = UNKNOWN 永不推断填补；无综合信任分；无 SAFE/INVALID 判决；audit/verify 只读；capture 只写 `runs/` 目录。

---

## 第二部分：禁止实现内容

以下清单为**硬禁令**，code review 时按此拒绝，任何人（包括实现者本人）不得以"顺手"为由纳入：

- GUI / Web dashboard / 任何前端
- Agent、多智能体、LLM 分析
- 自动修改实验（改代码、改配置、重跑、补跑）
- 自动恢复缺失信息（缺失字段的启发式填补；INFERRED 仍是 v0.1 规定的反推上限，capture 层不得伪造 CONFIRMED）
- 云端同步 / 托管服务 / 遥测 / 数据库
- W&B online API（网络调用；GMMVI 已证明其返回顺序不可验证，P0 §12）
- MLflow server 集成（本地文件 reader 也推迟到 v1.1）
- 自动调参 / 实验调度 / GPU 分配 / daemon
- 新规则 ED011+（规则数量冻结在 10）
- 第四/五个真实项目的 adapter 开发

依赖预算冻结：运行时依赖仍为 `pydantic / typer / PyYAML` 三件，**不新增**（git 信息经 `subprocess` 调系统 git，不引入 GitPython；哈希用 stdlib `hashlib`）。

---

## 第三部分：架构设计

### 3.1 目录布局（`src/experiment_doctor/`）

```
src/experiment_doctor/
├── capture/                 # 新增：Runtime Capture Layer
│   ├── git.py               #   commit/branch/dirty/diff_hash（subprocess 调 git）
│   ├── environment.py       #   python 版本、包版本 dump（importlib.metadata）、env-var 白名单
│   ├── hardware.py          #   CPU/GPU/内存（platform + 可选 torch 内省，torch 缺席时降级 UNKNOWN）
│   ├── runtime.py           #   子进程包装：spawn、stdio 透传、信号/exit code/stderr 尾部、心跳与起止时间
│   └── seed.py              #   从 argv 与 effective config 提取 seed（只提取有直接证据的键；否则 UNKNOWN）
├── lock/                    # 新增：lock 生命周期
│   ├── schema.py            #   LockFile pydantic 模型（§4），每字段 (value, grade, source)
│   ├── writer.py            #   启动即写 + 退出补写；自哈希 lock_hash
│   └── verifier.py          #   完整性重算 + 四类 drift 检测，产出 VerifyReport
├── bundle/                  # 新增：证据包
│   ├── manifest.py          #   runs/<id>/ → experiment_bundle/ 布局与 manifest.json
│   └── hashing.py           #   内容寻址（sha256）、hashes.json、覆盖检测
├── cli/                     # v0.1 cli.py 拆分（typer 子命令注册不变）
│   ├── init.py  run.py  verify.py  bundle.py          # 新增子命令
│   └── （scan/audit/rules/adapters 留在原 cli.py，行为不变）
├── schema.py  provenance.py rules/  audit.py  scanner.py  adapters/  report.py
│                            # ↑ v0.1 全部原样复用，零修改（见 3.2）
```

### 3.2 复用 / 新增边界

| 模块 | 处置 | 约束 |
|---|---|---|
| `schema.py`（ExperimentRun/Family/AggregationRecord、五值 grade、RunStatus、SpreadSemantics…） | **复用，零修改** | captured run 必须能无损装入 v0.1 `ExperimentRun` 字段集；装不下的信息留在 lock，不进 core schema（这是 v0.1 report round-trip 测试不漂移的前提） |
| `provenance.py`（ProvenanceField、SourceRef、不变式） | 复用，零修改 | capture 层写 source 时用 `artifact_id`/`path:key` 指向 lock/manifest——机制不变，只是来源从考古变一手 |
| `rules/`（ED001–ED010）+ `audit.py` | 复用，零修改 | MVP 验收要求三项目既有结论（21/21、46/46、25/25、19/19）逐条不变 |
| `adapters/`（generic/gmmvi-exp3/torchssl/crda） | 复用，零修改 | 新增 `captured` adapter（只读，把 `runs/` 布局映射为 ExperimentProject）是 MVP 唯一新增 adapter——它读的是自家格式，不引入外部维护负担 |
| `report.py` / `cli.py` 既有子命令 | 复用；cli.py 仅做子命令注册扩展 | report payload 契约（`project.model_dump(exclude={artifacts})` + `artifact_count`）不动 |
| `capture/` `lock/` `bundle/` | **全部新增** | 唯一的新代码面；对 v0.1 模块只 import 不修改 |

`captured` adapter 是架构上的关键决定：v1.0 的 run 产物**不绕过** v0.1 审计管线，而是作为第五个数据源进入同一管线。这样"capture → audit"的增益（ED002/003/004/009/010 从永远 INCONCLUSIVE 到基于一手记录 PASS）全部由既有规则语义给出，无需新规则。

---

## 第四部分：Experiment Lock Schema v1

`runs/<run_id>/experiment.lock.json`。每字段四元组：类型 / 必须? / 来源 / 缺失行为。**UNKNOWN 纪律**贯穿：所有 `source: none` 的字段 grade 一律 UNKNOWN 且 value 为 null，writer 不得写入任何推测值。

### identity
| 字段 | 类型 | 必须 | 来源 | 缺失行为 |
|---|---|---|---|---|
| `schema_version` | str | 是 | 常量 "1.0" | — |
| `run_id` | str(ULID) | 是 | writer 生成 | — |
| `created_at` | ISO8601 | 是 | 系统时钟 | — |
| `family_hint` | str\|null | 否 | ed.toml 或 argv 解析（仅当命令含显式 family/config 标识） | UNKNOWN（family 归并仍由 audit 层做） |
| `repetition_index` | int\|null | 否 | ed.toml 声明 | UNKNOWN |

### code
| 字段 | 类型 | 必须 | 来源 | 缺失行为 |
|---|---|---|---|---|
| `git_url` / `git_commit` | str\|null | 是(字段) | `git.py`：rev-parse / remote | 非 git 仓库 → value=null, grade=UNKNOWN, gap 登记（P0：GMMVI 0/7,004 命中证明此项不能省） |
| `git_dirty` | bool\|null | 是 | status --porcelain 非空 | UNKNOWN |
| `diff_hash` | str\|null | dirty=true 时必须 | `git diff` 内容 sha256 | dirty 且不可哈希 → grade=SUPPORTED 封顶（诚实降级；设计 §4 决策 2：记录现实而非拒绝运行） |
| `entrypoint` / `argv` | str / list[str] | 是 | run 命令行 | — |

### dataset
| 字段 | 类型 | 必须 | 来源 | 缺失行为 |
|---|---|---|---|---|
| `paths` | list[str] | 是(可为空) | ed.toml 声明 | 空 → fingerprint 全 UNKNOWN（不猜哪些文件是数据） |
| `fingerprint` | {path→sha256} | 声明了 paths 则必须 | hashing.py（目录取文件清单哈希） | UNKNOWN |
| `split_hash` | str\|null | 否 | ed.toml 显式指定 split 文件 | UNKNOWN |

### configuration
| 字段 | 类型 | 必须 | 来源 | 缺失行为 |
|---|---|---|---|---|
| `declared_hash` | str\|null | 是(可 null) | ed.toml 指定的 config 文件哈希 | UNKNOWN |
| `effective_file` | str\|null | 否 | `--config-dump` 约定路径或 ed.log | UNKNOWN → ED004 保持 INCONCLUSIVE（P0 §14：声明≠生效，归档常为子集，故两者分开存） |

### randomness
| 字段 | 类型 | 必须 | 来源 | 缺失行为 |
|---|---|---|---|---|
| `seed` | int\|null | 是(可 null) | `seed.py`：argv 的 `--seed` 类显式参数，或 effective config 中名为 seed 的键（仅直接证据） | **UNKNOWN，绝不从"通常约定"推断**（P0 §8：GMMVI seed 派生自外部包 + 丢失 stdout，正是推断会出错的形态） |
| `seed_derivation` | str\|null | 否 | 显式记录推导公式文本 | UNKNOWN |
| `determinism_flags` | dict | 否 | torch 内省（可用时） | UNKNOWN |

### environment
| 字段 | 类型 | 必须 | 来源 | 缺失行为 |
|---|---|---|---|---|
| `python` | str | 是 | sys.version | — |
| `packages` | {name→version} 或 file_hash | 是 | importlib.metadata 全量 dump | — |
| `hardware` | {cpu, gpu[], ram} | 是(可降级) | `hardware.py` | torch 缺席 → gpu=UNKNOWN（A2 §15：声明/运行时必须分字段，`requirements.txt` 类声明另存 `declared_environment`） |
| `cuda_driver` / `hostname` / `job_id` | str\|null | 否 | 内省 / 环境变量白名单 | UNKNOWN |
| `declared_environment_hash` | str\|null | 否 | ed.toml 指定的 env 文件 | UNKNOWN |

### execution
| 字段 | 类型 | 必须 | 来源 | 缺失行为 |
|---|---|---|---|---|
| `started_at` / `ended_at` | ISO8601 | started 必须 | runtime.py | 子进程被强杀 → ended=null, `termination_cause=UNKNOWN` + gap（P0 §11：`.bad` 混淆 OOM 与 outlier 的教训——终止因必须有信号级证据） |
| `exit_code` | int\|null | 是 | wait() | UNKNOWN |
| `termination_cause` | enum(ITERATION_CAP/TIME_LIMIT/CRASH/OOM/CONVERGED/UNKNOWN) | 是 | 信号 + stderr 尾部模式（仅白名单模式给 SUPPORTED，其余 UNKNOWN） | — |
| `stderr_tail` | file ref | 是 | 环形缓冲 64KB 落盘 | — |
| `compute_budget` | {wall_time_limit?, max_iters?, source} | 否 | 环境变量/SLURM 显式读取 | UNKNOWN（P0 §16：生效预算可藏在 gitignored 注入里，故存"来源"而非只有值） |
| `output_dir` | str | 是 | run 参数 | — |

### artifacts / metrics
| 字段 | 类型 | 必须 | 来源 | 缺失行为 |
|---|---|---|---|---|
| `files[]` | {path, sha256, role} | 是(可空) | 结束时扫描 output_dir + hashing.py | 空清单如实为空（P0 §24：MMD 列被覆盖——哈希清单使事后覆盖可检测） |
| `metrics_manifest[]` | {name, file, role, direction, selection} | 否 | ed.toml 声明或 ed.log | UNKNOWN → ED005 走 v0.1 反推路径（A1 §14：best−last 0.16–0.32 > spread 0.05，selection 不声明就不许进 CONFIRMED） |

顶层 `lock_hash`：对以上全部内容的规范化 JSON（sort_keys + 无空白）取 sha256，verify 重算比对。

---

## 第五部分：CLI 用户流程

### 主路径（研究生场景）

```bash
# 一次性：在项目根声明捕获策略（数据在哪、哪些 env var 可记、config 文件）
experiment-doctor init

# 原来的训练命令，前缀即得全部 provenance：
experiment-doctor run -- python train.py --seed 3 --data ./dataset

# 训练结束后（或提交论文前）：
experiment-doctor verify --all
```

`verify` 输出（五值状态，不合并成单一"健康度"）：

```
Experiment integrity  (run 01J…A3, lock_hash OK)

Code:        PASS    commit 4f2a1c9 (dirty, diff_hash b71e…) matches lock
Environment: PASS    python 3.11.9, 142 packages match lock
Seed:        PASS    seed=3 matches lock
Dataset:     DRIFT-DETECTED → FAIL
             dataset/images/train-012.png sha256 changed since run
Config:      UNKNOWN   no effective config captured (ED004 stays INCONCLUSIVE)

1 FAIL, 3 PASS, 1 UNKNOWN
```

要点：(a) UNKNOWN 显示为诚实的空缺而非绿色通过——A2 的 2185 INCONCLUSIVE / 0 虚假判决纪律在 UI 层的映射；(b) drift 检测的四种对象（code/config/environment/dataset）各自独立报告，因为 P0/A1/A2 证明它们以不同速率漂移（TorchSSL 的 `use_azure` 案例：code 漂移而其余不变，A1 §19–20）。

### 审计与证据路径

```bash
experiment-doctor audit runs/            # captured adapter → 完整 ED001–ED010
experiment-doctor bundle 01J…A3          # 生成 experiment_bundle/
#   experiment_bundle/
#     experiment.lock.json   （自洽，含 lock_hash）
#     manifest.json          （run→family→metric→文件角色索引）
#     hashes.json            （全部文件的 sha256；接收方离线复算）
experiment-doctor verify --bundle experiment_bundle/   # 第三方在另一台机器上核验包完整性
```

legacy 流程（`scan/audit --adapter gmmvi-exp3 …`、`--reported-table`）逐字不变，v0.1 用户零迁移成本。

---

## 第六部分：MVP 开发顺序

| Phase | 目标 | 预计文件 | 验收标准（gate，过则进下一阶段） |
|---|---|---|---|
| **1. Lock schema** | `lock/schema.py` + `writer.py` + `capture/` 六模块的纯函数部分（git/environment/hardware/seed + `hashing.py`）；无 CLI | 8 新文件 + 4 测试文件 | 模型 pydantic 校验通过；UNKNOWN 不变式测试（value=null ⇔ grade=UNKNOWN，仿 v0.1 provenance 测试风格）；lock_hash 规范化稳定（同内容两实例同哈希）；非 git 目录 / 无 torch / 无数据集路径三降级路径各有测试 |
| **2. Capture layer** | `capture/runtime.py`：真实 spawn 子进程 + 信号/stderr/exit 捕获 + execution 补写；`captured` adapter（runs/ → ExperimentProject，只读） | 2 新文件 + 1 adapter + 3 测试 | 用 `python -c` 假训练脚本跑通：正常退出 / SIGKILL / 非零码 / stderr 触发 OOM 白名单模式，四情形 lock.execution 与 grade 逐一断言；captured adapter 产出的 project 能通过 v0.1 `audit_project()` 不抛错 |
| **3. CLI** | `cli/init.py run.py bundle.py` + 注册；`bundle/manifest.py` | 5 新文件 + 2 测试 | §5 主路径命令端到端 exit 0；`--` 透传参数不被 typer 吞（argv 保真测试）；bundle 三文件齐且 hashes.json 可离线复算；既有 4 子命令输出与 0.1.0 逐字节一致（golden 对比） |
| **4. Verify** | `lock/verifier.py` + `cli/verify.py`：lock 自洽 + 四类 drift + `--bundle` 模式 | 2 新文件 + 2 测试 | §7 篡改矩阵 8/8 检出；未篡改项目 4 项全 PASS 且 UNKNOWN 如实显示；verify 全程只读（对 runs/ 目录做前后哈希快照比对） |
| **5. Integration** | synthetic 项目 fixture 全量 + 回归 + 门禁 + 文档 | 1 fixture 目录 + `tests/test_v1_integration.py` + `docs/v1/lock-format.md` | 设计规格书 §7 验收门全绿：mini train.py 3 seeds → verify 全绿 → audit 下 ED002/003/004*/009/010 基于一手记录 PASS（*ED004 需 config dump 约定生效）；v0.1 118 测试 + 三项目 acceptance 脚本本地重跑结论零漂移（此项**只在本阶段**跑，遵守既有效率纪律）；pytest/ruff/mypy 全绿 |

依赖链严格线性：1→2→3→4→5；Phase 3 起每阶段末允许一次 commit（前缀 `feat(v1):`），Phase 5 结束打 `v1.0.0-alpha.1`（仅本地/仓库 tag 线，**不做任何 PyPI 发布**——发布是后续独立任务书的事）。

工作量估计：新增源码约 1,800–2,400 行、测试约 1,200 行；单人 6–9 个工作日核心 + 3–4 天测试/回归/文档，3 个月预算内余量大，余量**不回灌功能**（边界冻结优先）。

---

## 第七部分：验收设计

### 7.1 Synthetic 项目 fixture（`tests/fixtures/v1/synthetic_project/`）

```
synthetic_project/          # git init 的完整小仓库
├── train.py                # 读 config.yaml，"训练"= 确定性伪计算，写 metrics.csv + checkpoint.bin
├── config.yaml
├── dataset/                # 3 个小文件
└── ed.toml
```

### 7.2 篡改矩阵（verify 的必检出清单，每项一个测试）

| # | 篡改 | 预期 verify 结果 | 证据锚点 |
|---|---|---|---|
| T1 | 提交 lock 后再 commit 一次（HEAD 前移） | Code FAIL（commit ≠ lock） | A1 §19–20：HEAD≠运行码必须可检出 |
| T2 | 保留 commit 号、改工作树文件（dirty 化） | Code FAIL（dirty 状态变化）或 diff_hash 不匹配 | P0 §15：commit 单独不足以定位 |
| T3 | 改 `dataset/` 任一字节 | Dataset FAIL（fingerprint 漂移） | §4 dataset 块存在的理由 |
| T4 | 改 config.yaml 中 lr | Config FAIL（declared_hash 漂移） | P0 §14：声明/生效分离 |
| T5 | 在 venv 里 `pip install` 一个额外包 | Environment FAIL（packages 集变化） | A2：声明 ≠ 运行时 |
| T6 | 手改 lock 里 seed 值 | lock_hash FAIL（自洽破坏），drift 检测不再进行 | lock 可信根；无此则 T1–T5 全可被伪造 lock 绕过 |
| T7 | 删除 lock 的 execution 块再重算哈希 | lock_hash FAIL（规范化哈希覆盖必含块） | T6 的变体防护 |
| T8 | 篡改 `hashes.json` 指向的 metrics.csv | bundle verify FAIL（内容寻址不匹配） | P0 §24：覆盖写检测 |

负向防护同样测试：未篡改 + 未声明数据集路径 → Dataset 显示 UNKNOWN 而非 PASS（**verify 不得把"没查"报成"通过"**——这是 A2 0/10 forbidden-inference 门禁在 v1.0 的对应物）。

### 7.3 回归要求（不可协商）

1. v0.1 既有 118 个测试（含 6 个 packaging 测试）在 v1.0 分支全部保持通过，其中锁定 schema/规则语义的测试**一个都不许改**；
2. 三项目本地 acceptance（GMMVI 21/21、TorchSSL 46/46、CRDA 25/25、rules 19/19）在 Phase 5 各重跑一次，结论逐条与冻结基线一致（`acceptance2-crda/evidence/` 等既有 JSON 为对照）；此后 Phase 无 core 修改则不再重跑（沿用既有效率纪律）;
3. `experiment-doctor scan/audit/rules/adapters` 对 legacy 项目的输出与 0.1.0 安装版做 golden diff，零差异；
4. 门禁链不变：pytest → ruff check+format → mypy（新增目录纳入 mypy 严格配置）。

---

## 第八部分：研究价值保持

**回答"v1.0 为什么不只是又一个 MLOps 工具"：** MLOps 追踪系统（MLflow/W&B/Sacred/DesignFlow）的目标函数是*记录与便利*——它们回答"发生了什么"，且默认记录者诚实。v0.1 的三项目实证恰好打在另一个问题上：**记录本身在科学上不可审计时会发生什么**。v1.0 的每个 capture 字段都对应一个已发生的、量化的恢复失败或语义错误：

| v1.0 机制 | 对应的 v0.1 实证 | 追踪系统为何给不出 |
|---|---|---|
| lock 于启动瞬间采样（commit/dirty/env/预算） | seed 0/3,483、commit 0/7,004（GMMVI）；runtime_environment 全缺（CRDA ×1,350） | 它们记录用户*选择上报*的内容，不强制上报"上报者身份"（代码/环境自身）；且无 UNKNOWN 概念——缺就是缺行，不是有等级的证据状态 |
| metrics_manifest 的 role + selection 声明 | best−last ≈0.23 > published spread 0.05（TorchSSL）；published=last 且符号取负误分类 25/107（GMMVI） | tracker 存全部曲线但不表达"发表的数代表哪条观测"这一科学决策 |
| verify 的漂移检测 + lock_hash | TorchSSL `use_azure`：clone 与归档可证伪地不一致 | tracker 不做"今天的现场 vs 当时的记录"对账 |
| audit 引擎复用（ED005–ED008 对 captured run 同样运行） | CRDA ED008 FAIL×270：prose 称 SEM、实现是 population std（40/40 票决）；TorchSSL prose "standard errors" vs 代码无 ÷√N | 这是"声明文本 × 实现 × 数值"三方对账，任何记录系统都不做 |
| evidence bundle（可转让、离线可验证） | v0.1 审计依赖人工转写 reported_table（自认的最薄弱环节，A1 §28.3） | tracker 的分享是仪表盘链接，不是第三方可重算的证据 |

**研究问题表述（论文与产品的同一命题）**：

> **How to make ML experiments scientifically auditable by construction?**
> ——把"可审计性"从考古学属性（事后、概率性、上限 INFERRED）改造为构造属性（运行时、确定性、可达 CONFIRMED），同时不牺牲审计侧的证据纪律（UNKNOWN 永不升格、无综合判决）。

v1.0 的可证伪假设即设计规格书 §7 的 MVP 命题：同一套 ED001–ED010 规则，在 capture-first 项目上，ED002/003/004/009/010 从三项目实测的"永远 INCONCLUSIVE"变为基于一手记录的 PASS——**规则的区分力由构造恢复，而非由放松纪律换取**。这正是与 MLOps 工具的分界：它们优化记录的丰富度，v1.0 优化证据的等级。

---

## 附：执行顺序速览

Phase 1 lock schema+capture 纯函数 → Phase 2 runtime+captured adapter → Phase 3 CLI(init/run/bundle) → Phase 4 verify → Phase 5 集成+回归+文档。每阶段 gate 不过不进下一段；全程不触 v0.1 冻结面（tag/PyPI/规则语义/schema）；本计划批准后下一动作是 Phase 1 编码（另行任务书启动）。
