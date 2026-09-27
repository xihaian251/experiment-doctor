# Experiment Doctor v1.0.0 — FINAL STATUS（文档冻结页）

- 日期：2026-09-27　阶段：Post-Release Freeze & Handoff
- 用途：给接手人的**单页契约陈述**——v1.0.0 保证什么、刻意不做什么、哪些接口已稳定、已知限制有哪些
- 规则：本页**只记录，不修复**。任何"看起来该顺手补"的项都属 v1.1 planning，需另立任务书
- 相关：发布过程 `V1_RELEASE_REPORT.md`；版本决策 `V1_RELEASE_FINAL_REPORT.md`；状态快照 `FINAL_RELEASE_STATE.md`；交接 `V1_HANDOFF_REPORT.md`

---

## 1. v1.0.0 保证什么（guarantees）

1. **两扇门**：任何进入证据记录的值只有两种来源 —— 直接观测（进程/文件系统/解释器）或显式声明（CLI 参数）。没有第三道门。二者皆无 ⇒ `UNKNOWN`（带原因，不是错误，也不阻断）。
2. **不宣称结果**：`termination_status = SUCCESS` 只表示被包装进程 `wait()` 返回 0；不表示训练成功、收敛或质量。`FAILED / TIMEOUT / INTERRUPTED / UNKNOWN` 同理为进程层面的观测词。
3. **不猜数值**：`stdout.log` / `stderr.log` 作为日志字节原样保存，从不解析为 metric；不存在任何自动指标推断。
4. **无评分**：没有 composite score、trust score、confidence score、overall verdict。规则逐条给五态状态（`PASS / FAIL / INCONCLUSIVE / NOT_APPLICABLE / NOT_RUN`），聚合层只有计数。
5. **可自证**：lock 与 run 各自携带规范化 JSON 密封（`lock_hash` / `run_hash`），run 通过**重算并交叉校验**引用 lock（绝不复制字符串）；`verify` 独立重放这两条链 + bundle 存在性 + 产物摘要 + 路径边界（V001–V006），退出码 `1` 当且仅当存在 `FAIL`。
6. **审计侧只读**：`scan / audit / rules / adapters` 不写被审计项目。写操作只发生在捕获侧（`init` / `run` 在**你自己运行的**项目根写 `experiment-evidence/`），且 `run` 会真实执行 `--` 之后的命令。
7. **加法而非破坏**：v0.1 的审计面（规则、schema、audit、scanner、provenance、四个验收 adapter）在 v1.0.0 中**逐字节未变**；10 条规则判定逻辑、severity、契约文档全部原样。
8. **确定性**：同一 bundle 反复 `verify` 与 `audit` 得到相同状态向量（Phase 5 以 `--repeat 2` 四个树验证过稳定性）。

## 2. v1.0.0 刻意不做什么（intentional absences）

| 不做 | 原因 |
|---|---|
| 从日志提取 metric / 汇总 accuracy | 一旦解析文本就是推断，违背第 1 节第 1、3 条 |
| 判断"实验是否成功/是否更好" | 属结论性宣称，工具层无权产出 |
| 自动重跑训练、自动调参、自动改进 | 工具是证据记录器与审计器，不是执行代理；亦为任务书长期禁止项 |
| agent / framework 编排 | 同上；不引入任何自主代理栈 |
| 压缩 / 上传 / 签名证据 | 会引入网络与凭据面，超出只读取证定位（v1 import 面无 `urllib/requests/http*/socket/zipfile/tarfile/gzip/sign`） |
| 综合信任分 | 见第 1 节第 4 条；README 自 v0.1 即明文声明 |
| 环境推断（未声明即 UNKNOWN） | `dataset.paths`、`artifacts.output_directory`、`runtime.timeout_*` 等未显式给出时保持 UNKNOWN，而非猜测 |

## 3. 稳定接口（stable interfaces）

以下四类 JSON/Markdown 结构在 v1.0.0 进入公开稳定期：**破坏性变更需 major**。字段级证据等级为 `CONFIRMED / SUPPORTED / INFERRED / UNKNOWN / CONFLICTING`（`INFERRED` 是启发式上限，永不升级为 `CONFIRMED`）。

### 3.1 `experiment-evidence/experiment.lock.json`

- `schema_version = "1.0"`（`src/experiment_doctor/v1/lock/schema.py`）；密封 = `sha256:` + 规范化 JSON（`sort_keys`、`separators=(",",":")`、`ensure_ascii=False`）之摘要，写入 `lock_hash`。
- 八个块（canonical 顺序：identity → code → dataset → configuration → randomness → environment → execution → artifacts），每字段带证据等级与来源：`identity`（experiment_id、created_at）、`code`（repository、commit、dirty、diff_hash）、`dataset`（paths、fingerprints）、`configuration`（config_files、config_hash）、`randomness`（seed、seed_source）、`environment`（python_version、packages、platform）、`execution`（command、cwd、start_time）、`artifacts`（**仅** output_directory；lock 阶段无 note 字段）。
- 契约文档：`docs/rules/` 十份 + `docs/v1/EXPERIMENT_DOCTOR_V1_DESIGN.md`。

### 3.2 `experiment-evidence/experiment.run.json`

- `schema_version = "1.0"`（`v1/run/schema.py`）；密封 `run_hash` 同上。
- `lock_reference`：路径 + **重算**的 lock_hash，与 lock 实际密封交叉校验。实测判定：`ref != 观测 lock_hash` ⇒ **V002 FAIL**；声明为 `UNKNOWN`（run 未做 lock-hash 声明）⇒ V002 `INCONCLUSIVE`；lock 无法重算 ⇒ V002 `INCONCLUSIVE`（缺失不是不匹配，也不是错误）。
- `execution`（command、cwd、pid、start_time、end_time、exit_code）、`runtime`（stdout_path、stderr_path、timeout_status、timeout_seconds）、`artifacts`（created_files / modified_files 的运行前后目录差分 + sha256、note）、`environment`（python_version、packages、platform）、`termination_status`。

### 3.3 verify 报告（`experiment-evidence/verify.json` / `verify.md`）

- `schema_version = "1.0"`；六项检查 **V001–V006**：密封自洽（lock、run 各一）、run→lock 链、bundle 四件套存在且非空、产物摘要匹配、路径边界不越界。**逐 ID 语义以 `V1_HANDOFF_REPORT.md` §4 的表为准**（实测：V001=lock 密封，V002=run→lock 链，V003=run 密封，V004=四件套，V005=产物摘要，V006=路径边界）。
- 每项四态；`NOT_APPLICABLE` 合法（例如 run 未声明任何产物写入时 V005 不适用）。
- 进程退出码 = 1 当且仅当存在 `FAIL`。

### 3.4 audit 报告（`report.json` / `report.md`，`audit -o <dir>`）

- 顶层键：`scan`、`audit`、`rules`、`rule_summary`、`project`（`report_payload` 生成；JSON 可 round-trip，由 `tests/test_packaging.py` 锁定）。
- `rules[]` 每条含 `rule_id`（ED001–ED010）、`entity_type`、`entity_id`、`status`、`severity`、`summary`、`measurements`、`limitations`、`recommendation`。
- `rule_summary.counts` 给每规则的五态计数；**无**任何综合分字段。
- 规则集恰好 10 条且顺序为 `ED001..ED010`（测试锁定）；命令面恰好 7 个：`scan audit rules adapters init run verify`（测试逐命令 `--help` 锁定）。
- `captured` adapter：把 lock+run+日志映射进上述 v0.1 模型，bundle 在场且完好时自动选中；引用一律落在 bundle 文件上以满足 `attached_to_run`。

## 4. 已知限制（只记录，不修复）

任务书点名的四项：

| # | 限制 | 现状事实 |
|---|---|---|
| A1 | **tracker 集成缺失** | 无 MLflow / W&B / SwanLab / Neptune 读取路径；实验身份只来自本机 bundle 与 `identity.experiment_id` |
| A2 | **MLflow / Hydra 缺失** | 不解析 `mlruns/`、`mlflow.db`；不读 Hydra `overrides.yaml` / `.hydra/` 配置树。声明配置只走 `--config` 显式给定的文件（其哈希 `CONFIRMED`，语义不解释） |
| A3 | **metric 提取缺失** | 见第 2 节第 1 条。`captured` 路径下 `MetricRecord` 不产生；审计有 metric 的能力仅存在于 v0.1 的验收 adapter（读项目自己写出的结构化结果文件） |
| A4 | **删除检测受限** | 全树差分能识别 created / modified；被删除的文件**只进 `artifacts.note` 的自由文本**，没有结构化 deleted 字段（结构化 deleted 属 v1.1 候选） |

其余仍有效的限制（完整清单见 `V1_RELEASE_FINAL_REPORT.md` §6 的 L1–L13 与 `V1_RELEASE_REPORT.md` §9）：capture 为 forward-only（对从未捕获的历史归档无能为力）、无 hardware/CUDA 捕获、`artifacts.output_directory` 未声明即 UNKNOWN、sdist 不可字节复现、`pyproject.toml` 的 `description` / 包 docstring / `cli.py` 帮助文案仍是 v0.1 措辞（"Read-only …"），以及仓库内 4 组 v0.1 既有本机绝对路径（属已发布历史证据，不删）。

## 5. 冻结声明

自 `fb3a242`（tag `v1.0.0`）起：schema 字段语义、ED001–ED010 判定与 severity、audit pipeline、adapter 语义、CLI 命令面**冻结**。其后的提交只能是文档、测试补充、构建/发布基础设施，或在 v1.1 planning 授权下的功能变更。
