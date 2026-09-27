# Phase 5 报告：Final Validation（v1.0 MVP 端到端最终验证）

- 日期：2026-09-27
- 范围：v1.0 实施计划 Phase 5。前置：Phase 1（lock）/ Phase 2（run + bundle）/
  Phase 3（verify V001–V006）/ Phase 4（captured adapter）——四份 PHASE 报告已复核，
  四类产物均在树中存在并可导入
- 状态：**完成**。未 release；未进入 v1.1；未扩展功能；未 commit
- 性质：**纯验证阶段**。本轮新增文件 2 个（验证驱动脚本 + synthetic fixture），
  修改已跟踪文件 **0 个**，删除 1 个 Phase 4 遗留空目录
  （`tests/fixtures/v1_captured_project/`，空、未跟踪、本轮自建自清）
- 结果速览：真实 CLI 全链路 `init→run→verify→audit` 两次独立重复，ED001–ED010
  状态向量**逐字节一致**；四套遗留验收 **21/46/25/19 全通过且与历史 JSON sha256
  完全相同**；全量 `212 passed, 1 skipped`；ruff check / format --check（83 files）/
  mypy（64 files）全绿；网络调用零命中、凭据读取零命中、外部真实仓库 audit 后
  零文件改动且 git 状态干净
- 过程说明：消息挂载的 crewai / autogpt / autoresearch / creative-thinking 四个
  skill 与本阶段边界（不新增功能、不创建 Agent、只做确定性验证）冲突，**未加载执行**。

---

## 1. MVP architecture final state

工作树状态（Step 0 冻结）：

```
HEAD (SHA)  e17ab18cf087e1410259f110150fa16d49429373   ← v0.1 已发布提交，未移动
git status  3 modified / 12 untracked（v1 全部工作为未提交增量）
  M src/experiment_doctor/adapters/__init__.py   (+2，注册 captured)
  M src/experiment_doctor/cli.py                 (+16/-4，Phase 2–3 注册行)
  M tests/test_packaging.py                      (+2/-1，Phase 4 registry 期望集)
  ?? src/experiment_doctor/v1/                   (Phase 1/2/3)
  ?? src/experiment_doctor/adapters/captured.py  (Phase 4)
  ?? tests/fixtures/v1_{basic,run,verify,audit,full}_project/
  ?? tests/test_v1_{lock_capture,run_capture,verify,audit_integration}.py
  ?? scripts/run_v1_full_pipeline_check.py       (Phase 5)
```

分层与规模：

| 层 | 文件 | 行数 | 本轮是否改动 |
|---|---|---|---|
| v0.1 audit 核心 | `audit.py` / `schema.py` / `scanner.py` / `provenance.py` | 820 / 632 / 328 / 138 | 否 |
| v0.1 规则 | `rules/`（base + 10 条规则） | 1839 | 否（`git diff` 对 HEAD 为空） |
| v1 Phase 1 lock | `v1/lock/` + `v1/capture/` | 315 + 225 | 否 |
| v1 Phase 2 run | `v1/run/` | 462 | 否 |
| v1 Phase 3 verify | `v1/verify/` | 540 | 否 |
| v1 CLI | `v1/cli.py` | 110 | 否 |
| v1 Phase 4 adapter | `adapters/captured.py` | 378 | 否 |

CLI 注册命令恰为 7 个：`scan / audit / rules / adapters`（v0.1 四个，实现字节未动）
`+ init / run / verify`（v1 新增，additive 注册）。

链路职责边界（本轮实测确认，非文档复述）：

```
init    → experiment.lock.json          （声明 + 观测，逐叶打 grade）
run     → experiment-evidence/{lock, run, stdout.log, stderr.log}
verify  → V001–V006 + verify.json/md     （确定性重算，只读四类证据文件）
audit   → captured adapter → ED001–ED010 （翻译 grade，不新增观测）
```

## 2. End-to-end pipeline

驱动：`scripts/run_v1_full_pipeline_check.py`，全程调用**真实 CLI 子进程**
（`python -m experiment_doctor ...`），不走库内捷径。任务书流程与实际命令的对应：

| 任务书 | 实际命令 |
|---|---|
| `experiment-doctor init` | `init <proj> --seed 123 --config config.yaml --command "python train.py --seed 123"` |
| `experiment-doctor run -- python train.py` | `run --path <proj> -- <python> train.py --seed 123` |
| `experiment-doctor verify evidence/` | `verify <proj>`（bundle 目录名为 `experiment-evidence/`，非 `evidence/`；也可传 bundle 目录本身） |
| `experiment-doctor audit evidence/` | `audit <proj> -o <out>` |

四棵独立树，各自回答一个问题：

| 树 | 构造 | 回答 |
|---|---|---|
| `pre` | 只有 fixture（未跑、未提交、无 bundle） | 证据完全不存在时规则**根本不产出结果**（见 §3 说明） |
| `trad` | 普通 `python train.py` 跑出 `results/`，无 git、无 bundle | 传统工作流的审计上界 |
| `cap` | 同一棵树**先**（git 历史 + results，无 bundle）审计一次，**再** init→run→verify 后审计一次 | capture 前后的差分；唯一变量是 bundle |
| `noseed` | `init` 不给 `--seed`，但命令行里有 `--seed 123`，stdout 里有 `accuracy=99.0` | 防火墙：这些字符串不得换来任何 PASS |

## 3. Synthetic golden result（Step 1）

fixture：`tests/fixtures/v1_full_project/{train.py, config.yaml}`。`train.py` 故意
(a) 接收 `--seed`、(b) 往 stdout 打印 `accuracy=99.0 loss=0.001`、(c) 写
`results/metrics.csv`——即"看起来像指标"的三处诱饵，用来证明审计链一个都不读。

`--repeat 2` 两次独立完整构造，**十格状态向量完全相同**
（`status_vectors_stable: true`，脚本对不等情形返回非零退出码）。

### 3.1 同一棵树 capture 前 → capture 后

```
adapter generic -> captured        runs 1 -> 1        verify: V001–V006 全 PASS
ED001  NOT_APPLICABLE  same  NOT_APPLICABLE
ED002     INCONCLUSIVE   ->  PASS
ED003     INCONCLUSIVE   ->  PASS
ED004     INCONCLUSIVE  same  INCONCLUSIVE
ED005          ABSENT   same  ABSENT
ED006          ABSENT   same  ABSENT
ED007          ABSENT   same  ABSENT
ED008          ABSENT   same  ABSENT
ED009     INCONCLUSIVE  same  INCONCLUSIVE
ED010   NOT_APPLICABLE   ->  PASS
```

三条变化各有独立来源，无人工干预：ED002 因 lock 记录了 seed；ED003 因 lock 记录了
commit；ED010 因 run record 捕获了解释器/包/平台。四条不变同样是结论而非遗漏：
ED004（lock 只有 config 路径+哈希，无生效值）、ED009（退出码不是停止原因）、
ED001（单 run 家族无身份可比）、ED005–ED008（无 aggregation 实体，规则**不产出结果**，
记作 ABSENT）。

### 3.2 另两棵树（如实记录与任务书示例的偏差）

- `pre`（项目里什么都没有）：**0 条规则结果**。任务书的对照假设是"全 UNKNOWN"，
  实际 v0.1 语义是"没有 run 实体就没有可判对象"→ 连结果都不生成。本轮未为此
  改核心（禁改），改为把 `trad`（有产物、无 bundle）作为有意义的 before 基线。
- `trad`：ED002 **INCONCLUSIVE**（与任务书一致）、但 ED010 是 **NOT_APPLICABLE**
  而非示例里的 INCONCLUSIVE，规则原文：*"no runtime record and no dependency
  declaration exist anywhere, so this run carries no environment claim to check"*。
  **未为凑示例而修改任何判定**；capture 后该格确实变成 PASS，演示结论不受影响。

### 3.3 verify 侧一个值得登记的诚实细节

`cap` 树在 capture 之前已用普通方式跑过一次 `train.py`，产物字节与重跑完全相同，
因此 Phase 2 的全树 sha256 快照差分观察到 **0 条 created/modified**，run record 里
`artifacts.created_files/modified_files` 如实为 UNKNOWN（note："no created changes
observed"），V005 于是给出 **NOT_APPLICABLE** 而不是编造一条"已确认写出"。
未预跑过的 `noseed` 树则 V001–V006 **全 PASS**。两种结果都是对的，差别只在证据本身。

## 4. Legacy regression（Step 2）

输入路径不猜，全部从历史 acceptance JSON 自带的 `inputs` 块读回后重跑：

| 套件 | 脚本 | 结果 | 与历史 JSON（Phase 4 冻结 `tmp/*_p4.json`）sha256 |
|---|---|---|---|
| GMMVI | `run_gmmvi_acceptance.py` | **21/21** | `23fff61805dff0c2` == `23fff61805dff0c2` **相同** |
| TorchSSL | `run_torchssl_acceptance.py` | **46/46** | `a2282b9a44b0c5e1` == `a2282b9a44b0c5e1` **相同** |
| CRDA | `run_crda_acceptance.py` | **25/25** | `1f4bedaa1b937312` == `1f4bedaa1b937312` **相同** |
| Rule acceptance | `run_rule_acceptance.py` | **19/19** | `199462cbf6743eff` == `199462cbf6743eff` **相同** |

任务书允许 timestamp/path/duration 差异；实测递归逐字段 diff 结果为
**total_diffs=0（四套皆是）**——这些 acceptance JSON 本身不落时间戳，因此差异
不需要豁免，`passed/failed` 与 21/46/25/19 条 check 全部一字未变。
**rule result drift：0。**

## 5. UNKNOWN reduction evidence（Step 3）

只统计状态计数与证据可得性，不打分、不排序、不使用 better/worse 措辞。

### 5.1 规则维度（capture 前 → capture 后）

| 规则 | before | after | 状态变化 | 变化原因（证据可得性） |
|---|---|---|---|---|
| ED001 | NOT_APPLICABLE | NOT_APPLICABLE | 无 | 家族仍只有 1 个 run |
| ED002 | INCONCLUSIVE | **PASS** | 是 | `randomness.seed` 进入 lock，引用落在 run 本地 artifact |
| ED003 | INCONCLUSIVE | **PASS** | 是 | `code.commit` 进入 lock |
| ED004 | INCONCLUSIVE | INCONCLUSIVE | 无 | 生效配置仍未被捕获（只有路径+哈希） |
| ED005 | ABSENT | ABSENT | 无 | 无 aggregation 实体 |
| ED006 | ABSENT | ABSENT | 无 | 同上 |
| ED007 | ABSENT | ABSENT | 无 | 同上 |
| ED008 | ABSENT | ABSENT | 无 | 同上 |
| ED009 | INCONCLUSIVE | INCONCLUSIVE | 无 | 退出码不构成 `TerminationCause`；未触发超时 |
| ED010 | NOT_APPLICABLE | **PASS** | 是 | run record 的 environment 块出现（此前无任何环境声明） |

统计：状态发生迁移的规则 **3/10**；保持 UNKNOWN 语义（INCONCLUSIVE）的 **2/10**；
保持 NOT_APPLICABLE 的 **1/10**；ABSENT（无实体）的 **4/10**；
**没有任何规则迁移到 FAIL，也没有任何 PASS 是靠推断得到的。**

### 5.2 字段维度（v0.1 冻结的 `COVERAGE_FIELDS` 口径，UNKNOWN 计数 1→0）

转为有据（7 个）：`seed`、`code_commit`、`code_dirty`、`command`、
`config_source`、`start_time`、`end_time`。

保持 UNKNOWN（18 个）：`compute_budget`、`dataset`、`dataset_version`、`entrypoint`、
`exclusion_category`、`exclusion_evidence`、`exclusion_reason`、`history_rows`、
`included_in_aggregation`、`method`、`metric_direction`、`metric_value`、
`repetition_index`、`resolved_config`、`runtime_seconds`、`task`、`termination_cause`、
`tracker_run_id`。

`runtime_environment` 不在 v0.1 的冻结覆盖清单里（ED010 却由它驱动），故由驱动脚本
直接从 project dump 统计，不改动核心：
`python_version / framework_versions / os` → **CONFIRMED**；
`cuda_version / hardware` → **UNKNOWN**（bundle 无加速器证据）。

## 6. Security audit（Step 5）

| 检查 | 方法 | 结果 |
|---|---|---|
| 凭据词汇 | `grep -rniE "password\|passwd\|secret\|credential\|api_key\|access_key\|private_key\|bearer\|authorization" src/ tests/` | **src 0 命中**；tests 仅 4 命中，全在 Phase 2 安全测试自身（`RUN_KEYS` 清单、`ED_CANARY_PASSWORD` 诱饵、测试名与 docstring）。裸词 `token` 的命中均为字符串切分变量名/散文用词 |
| 环境变量读取 | `grep -rn "os.environ\|getenv" src/` | **0 命中**：lock/run 从不采集环境变量，因此不存在"把凭据抄进 bundle"的路径；子进程靠默认继承（Phase 2 已测） |
| 网络 / 上传 / 远程写 | `grep -rniE "socket\|urllib\|requests\|httpx\|aiohttp\|urlopen\|ftplib\|smtplib\|paramiko\|boto3\|s3\|oss2\|websocket\|grpc\|http.client" src/ tests/ scripts/` | **0 命中** |
| v1 依赖面 | 逐文件 import 清点 | 仅标准库（`hashlib/json/platform/shutil/subprocess/sys/uuid/dataclasses/enum/typing/pathlib/datetime`）+ pydantic + typer + 本包自身；无第三方网络/云 SDK |
| git 只读 | 枚举 `v1/capture/git.py` 实际调用的子命令 | 仅 `rev-parse / remote get-url / status --porcelain / diff / ls-files`；**无** `init/add/commit/checkout/reset/clean/push` → 不改历史 |
| 写入面全清点 | 枚举 src 全部 write-capable 调用 | **12 处**，全部写自有输出：`v1/run/runner.py` 5（bundle 四件套）、`v1/verify/checks.py` 2（verify.json/md）、`v1/lock/writer.py` 1（lock）、`report.py` 3（report.json/md）、`cli.py` 2（`scan --json`）。**audit 路径（`adapters/`、`audit.py`、`rules/`、`scanner.py`、`provenance.py`、`schema.py`）0 命中** |
| 外部实验目录不被修改（真实项目实测） | 对 CRDA 与 TorchSSL 两个真实 clone 各跑一次完整 audit，随后 `find -newer` 列改动文件 + `git status --porcelain` | 两仓库**新于运行起点的文件数 0**；两仓库 `git status --porcelain` **0 行** |
| 对已捕获项目零写入（哈希实测） | 快照 13 个文件 sha256 → `verify` → 再快照 → `audit` → 再快照 | verify 新增 0 / 改动 0（verify.json/md 重写后字节相同，同时是确定性证据）；audit 新增 0 / 改动 0 |

边界声明（不属于漏洞，如实写明）：`run` 会执行**用户自己的命令**，该子进程写什么由
用户代码决定，wrapper 不做沙箱、不做拦截；wrapper 自身的写入全部落在项目内的
`experiment-evidence/`（Phase 2 已用 V006 路径边界与专项测试固化）。

## 7. 质量门禁（Step 6）

```
pytest -q                     212 passed, 1 skipped   (3:42)
  v0.1 legacy                 119 collected = 118 passed + 1 skipped   （数字未变）
  Phase 1 test_v1_lock_capture        21
  Phase 2 test_v1_run_capture         22
  Phase 3 test_v1_verify              19
  Phase 4 test_v1_audit_integration   32
  v1 合计                     94
ruff check .                  All checks passed!
ruff format --check .         83 files already formatted
mypy src scripts tests        Success: no issues found in 64 source files
```

Phase 5 **未新增 pytest 用例**（任务书 Step 6 的期望总数即 212），端到端验证以
`scripts/` 驱动脚本 + golden JSON 形式固化，与四套 acceptance 脚本同构。

核心冻结复核：`git diff --stat` 覆盖 `audit.py rules/ schema.py scanner.py
provenance.py` + gmmvi/torchssl/crda/generic 四个验收 adapter → **输出为空**；
`git diff --quiet -- src/experiment_doctor/rules` → rules/ 与 HEAD 字节相同。

## 8. Known limitations

1. **一个 bundle 一个 run**：ED001 与 ED005–ED008 在 captured 路径上永远无对象可判
   （ABSENT，不是通过）。跨 bundle / 多样本聚合不在 MVP 范围。
2. **生效配置不可得**：lock 只指纹 config 文件，ED004 结构性停在 INCONCLUSIVE。
3. **数据集 / 方法 / 任务身份缺失**：bundle 无这些概念的位置，18 个字段的 UNKNOWN
   中有 6 个（`dataset`、`dataset_version`、`method`、`task`、`entrypoint`、
   `tracker_run_id`）源于此。
4. **终止原因几乎总为 UNKNOWN**：只有 wrapper 自己施加的超时能映射；被信号杀、
   OOM、被抢占都不作推断。本轮 golden 未触发超时，故 ED009 的 PASS 路径只在
   Phase 4 测试中覆盖，未在 golden 中出现。
5. **无硬件/加速器证据**：`cuda_version`、`hardware` 恒 UNKNOWN，ED010 的 PASS 只
   覆盖解释器 + 包 + 平台三项。
6. **时间无外部锚**：start/end 来自 capture 时系统时钟，只做格式换算，不做校准。
7. **audit 不判篡改**：篡改归 verify。单独运行 `audit` 时，被改过内容的 bundle 仍会
   被忠实读成字段（本轮以 `find`/`git status` 与哈希快照证明的是"不写"，不是"不坏"）。
8. **签名/防重放缺位**：懂 canonical 契约者可同时重算两个哈希整体重封印；bundle 级
   签名被任务书明令禁止，抵御需外部 trust anchor。
9. **golden 的 before 基线不唯一**：`pre`（什么都没有）产出 0 条规则结果，因此
   §3.1 的差分选用"有产物、有 git、无 bundle"作为 before。换一个 before 构造，
   UNKNOWN 起点就不同——这是口径选择，不是缺陷，但复用本报告时需按同一定义。
10. **fixture 是合成的**：`v1_full_project` 证明的是链路连通与不推断，**不**证明
    真实训练负载（大日志、并发写出、非零退出、容器内 git）下的一致表现；真实项目
    侧只验证了 audit 只读性与遗留规则零漂移。

## 9. Release readiness decision

**判定：v1.0 MVP 的功能面已达到"可发布候选"的技术门槛，但本阶段不执行发布，
且发布前尚有下列必须由人拍板的前置项。**

支持"门槛已达"的实测依据：

1. 目标链路 `init → lock → run → verify → captured adapter → ED001–ED010` 在真实
   子进程上跑通，两次独立重复状态向量完全一致（§3）。
2. v0.1 全部黄金数字零漂移：118+1 原生用例、21/46/25/19 四套真实项目验收，且四套
   输出与历史 JSON **sha256 相同**（§4）。
3. 判定逻辑与 severity 未被触碰：`rules/` 与 HEAD 字节相同，规则目录仍恰好
   ED001–ED010（`ED01[1-9]` 在 src 内 0 命中）。
4. 反推断边界在流水线级别成立：命令里的 seed、stdout 里的 metric、落盘的
   metrics.csv 三处诱饵同时存在时，ED002 仍 INCONCLUSIVE、metric of record 仍为空、
   ED005–ED008 仍不产出结果（§3.2 noseed 树）。
5. 安全面干净：网络零命中、环境变量读取零命中、git 只读、写入面 12 处且全为自有
   输出、真实外部仓库 audit 后零改动（§6）。
6. 三条静态门禁全绿（§7）。

发布前需人决定的前置项（本轮按禁令**全部未做**）：

1. **commit**：v1 Phase 1–5 至今是 12 项未跟踪 + 3 项修改的工作树增量；HEAD 仍是
   v0.1 已发布提交 `e17ab18`。发布需先决定提交切分与是否并入已发布分支。
2. **版本号与 changelog**：v1.0 是 minor 还是 major、`pyproject.toml` 版本、
   CHANGELOG 措辞。
3. **发布通道**：PyPI Trusted Publishing 与 GitHub Release（v0.1 已建立该流水线），
   任务书此处明令"不要 release / 不要修改 v0.1 release"。
4. **§8 第 1/2/3 条是否算 MVP 完备**：ED004 与 ED005–ED008 在 captured 路径上
   不产出 PASS 是设计后果；若对外文案称"可验证可复现性"，需确认该表述与
   "单 bundle 单 run、无生效配置、无指标"这一实际覆盖面一致。
5. **依赖面**：`src` 未新增任何第三方依赖（已核），但发布前仍需在 fresh venv 安装
   wheel 复跑 smoke（v0.1 发布流程有这一步，本轮未做）。

**本阶段行动边界遵守情况**：未 release、未打 tag、未 commit、未进入 v1.1、未扩展
功能、未修改 v0.1 已发布内容、未新增规则/schema 字段/adapter。

---

*Phase 5 交付终点，v1.0 MVP 验证闭环完成。工作树保持未提交状态。*
