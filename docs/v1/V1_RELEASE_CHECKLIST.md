# Experiment Doctor v1.0 — Release Checklist（RC 整理，不发布）

- 日期：2026-09-27
- 阶段：Release Candidate Preparation（Step 5 交付物）
- 前提：Phase 1–5 全部完成（`PHASE1..PHASE5_*_REPORT.md`），HEAD 与工作树状态见 §0
- 状态更新（RC Resolution，同日）：本文件为 **RC1 时点快照**，正文事实与数字未改写。其中 B2（文档在仓库外）已通过把 `../docs/v1_design/` 迁入库内 `docs/v1/` 解决、B4（README/CHANGELOG 不描述 v1）已按 D4 补写、B3 版本号**未**改动仍待决策；逐项处置见 `V1_RELEASE_CANDIDATE_RC2_REPORT.md` §1。
- 状态更新（RC Final，同日）：§1 的三条 TODO（版本号 0.1.0 / 语义化判定 / `description` 文案）中，**版本决策已定为 `1.0.0` 并落地**（`__init__.py:__version__` + `test_packaging.py:RELEASE_VERSION`，commit `717e3cf`），本文件 §1 表内的 `"0.1.0"` 字样为快照原文不再更新；`description` 文案经人工确认本轮不动（报告 §6 L9）。发布就绪判断与待授权动作见 `V1_RELEASE_FINAL_REPORT.md` §7。
- 状态更新（Public Release Execution，同日）：**v1.0.0 已正式发布** —— release commit `fb3a242`、annotated tag `v1.0.0`、GitHub Release 与 PyPI 双上线（Trusted Publishing，无 token/twine）。本文件 §3 的 CLI 文案 TODO、§5 的路径剥离 TODO 仍未处理，属发布后的非阻塞项。全过程见 `V1_RELEASE_REPORT.md`。
- 本清单只做**事实登记 + DONE/TODO 标记**。本轮未修改任何代码、未 commit、未 push、未 tag、未发布。

标记含义：**DONE** = 已验证为真；**TODO** = 需要人工决策或发布动作，本轮不代为执行。

---

## 0. 冻结状态（读取，未改动）

| 项 | 值 |
|---|---|
| 仓库根 | `git rev-parse --show-toplevel` 的结果，即本仓库顶层；下文记作 `<repo>`。仓库根的同级目录记作 `<parent>/` |
| HEAD | `e17ab18cf087e1410259f110150fa16d49429373`（`docs: record published 0.1.0`） |
| 分支 / 远端 | 本地 `main` 跟踪 `origin/master`；`origin = https://github.com/xihaian251/experiment-doctor.git`；`ahead/behind = 0/0` |
| 已发布锚点 | tag `v0.1.0` → `7c9e5506efecb7f0b96b038bd431783329d0c895`（HEAD 的祖先） |
| 未提交改动 | 3 个 M：`src/experiment_doctor/adapters/__init__.py`、`src/experiment_doctor/cli.py`、`tests/test_packaging.py` |
| 未跟踪 | 12 条（`src/experiment_doctor/v1/` 15 个 .py、`adapters/captured.py`、`scripts/run_v1_full_pipeline_check.py`、5 个 `tests/fixtures/v1_*` 目录、4 个 `tests/test_v1_*.py`） |
| 核心冻结 | `git diff` 对 `rules/` `schema.py` `audit.py` `scanner.py` `provenance.py` 及 4 个 acceptance adapter **为空**；`git diff --quiet -- src/experiment_doctor/rules` → rules 与 HEAD 逐字节一致 |

---

## 1. Version

| 状态 | 事实 |
|---|---|
| DONE | 版本单一来源成立：`src/experiment_doctor/__init__.py` `__version__ = "0.1.0"`；`pyproject.toml` 把 `version` 放进 `dynamic`，由 `attr = "experiment_doctor.__version__"` 读取，无第二处版本号 |
| DONE | 打包锁测试存在并生效：`tests/test_packaging.py` 的 `RELEASE_VERSION = "0.1.0"` + `test_version_is_frozen_and_single_sourced` |
| DONE | 本轮构建出的 wheel 自述版本为 `experiment_doctor-0.1.0-py3-none-any.whl`（与源码一致，无版本漂移） |
| **TODO** | 当前版本号仍是 **0.1.0**，不是 1.0。升为 `1.0.0` 需要**同时**改 `__init__.py:__version__` 与 `tests/test_packaging.py:RELEASE_VERSION`（两处由测试锁定，改一处必红）。本轮为"不增加功能、不发布"阶段，故未改 |
| **TODO** | 语义化版本判定留给人工：v1 新增 `init/run/verify` 与 `captured` adapter，对 v0.1 四命令为**纯加法**（未破坏既有 CLI/JSON 契约），是否按 major（1.0.0）还是 minor（0.2.0）发布需决策 |

## 2. Package metadata

| 状态 | 事实 |
|---|---|
| DONE | `name = "experiment-doctor"`；`requires-python = ">=3.11"`；`license = "Apache-2.0"` + 仓库根 `LICENSE`（11,358 字节）；`authors = [{name = "beihai"}]`（ASCII，不含本地用户名） |
| DONE | 运行时依赖仅 3 个：`pydantic>=2.5`、`typer>=0.12`、`PyYAML>=6.0`；v1 新代码的 import 面（全量列举，共 20 个模块）**不含任何网络、压缩、签名库**：`hashlib json pathlib platform subprocess sys uuid typer pydantic datetime enum dataclasses collections.abc importlib.metadata typing experiment_doctor.*` |
| DONE | 入口点 `experiment-doctor = "experiment_doctor.cli:main"` 在干净安装下可执行（§3） |
| DONE | wheel 载荷干净：48 条目 / 42 个 `.py`，**无** `__pycache__`、`.pyc`、`.json`、`.log`、`.csv`；顶层只有 `experiment_doctor/` 与 `experiment_doctor-0.1.0.dist-info/`；`src/experiment_doctor/v1/**` 15 个模块与 `adapters/captured.py` 均在包内 |
| DONE | `scripts/`（5 个 acceptance 驱动 + 1 个 v1 流水线驱动）与 `tests/` **不进 wheel**：属仓库内开发工具，非发行物 |
| **TODO** | `description` 仍为 `Read-only provenance and aggregation audit for ML experiment artifacts`。v1 的 `run` 会**执行用户命令**、`init/run` 会在项目根写自身证据文件；"read-only" 只对 `scan/audit/rules/adapters/verify` 成立。文案修正属发布决策，本轮未改（同类：包 docstring `The tool never writes into the audited project`，对 audit 路径仍准确） |

## 3. CLI

| 状态 | 事实 |
|---|---|
| DONE | 注册命令共 7 个：`scan audit rules adapters init run verify`（`experiment-doctor --help` 实测输出） |
| DONE | **干净安装端到端**（`tmp/rc_venv`，`pip install .`，非 editable）：`experiment_doctor.__file__` 解析到 `tmp/rc_venv/Lib/site-packages/experiment_doctor/__init__.py`；site-packages 内**无** `__editable__*` / `*.egg-link` / `*.pth` 指回源树 |
| DONE | 安装副本在仓库外目录跑通全链：`init`（退出 0，`lock_hash sha256:4bce809e…`）→ `run -- python train.py --seed 7`（`termination: SUCCESS`，`run_hash sha256:ea083780…`，`lock_reference` 与 lock 一致）→ `verify`（V001–V006 **全 PASS**，退出 0）→ `audit`（`adapter=captured families=1 runs=1 rules=6 fail=0 inconclusive=2`，退出 0） |
| DONE | 安装副本 audit 的 10 规则状态向量与 Phase 5 golden 的 `cap` 向量**逐项相同**（`ED001 NOT_APPLICABLE / ED002 PASS / ED003 PASS / ED004 INCONCLUSIVE / ED009 INCONCLUSIVE / ED010 PASS`） |
| **TODO** | 组帮助文本仍写 `Experiment Doctor v0.1: ... (read-only)`；三个 v1 命令已在注册表内但顶层描述未提。文案更新与版本决策一并处理 |
| **TODO** | `experiment-doctor --version` 不存在（v0.1 亦无）。是否补属功能决策，本轮"不增加功能"→ 不加 |

## 4. Tests

| 状态 | 事实 |
|---|---|
| DONE | 全量本地门禁（本轮 Step 6 重跑）：`212 passed, 1 skipped`；`ruff check .` → All checks passed；`ruff format --check .` → 83 files already formatted；`mypy src scripts tests` → no issues in 64 source files |
| DONE | v1 测试量：21（lock）+ 22（run）+ 19（verify）+ 32（audit integration）= 94；v0.1 legacy 118+1 **零漂移** |
| DONE | 遗留真实项目回归（Phase 5 Step 2 记录，本轮**未重跑真实仓库**）：GMMVI 21/21、TorchSSL 46/46、CRDA 25/25、Rule 19/19，四份输出与 Phase 4 基线 **sha256 全等**（`23fff618…/a2282b9a…/1f4bedaa…/199462cb…`） |
| DONE | 端到端稳定性：`tmp/p5/golden.json` `status_vectors_stable: true`（`--repeat 2`，四个树的 10 规则向量逐次相同） |
| DONE | 唯一 skip 为环境性跳过：`tests/test_packaging.py:48`「source-tree run: the distribution is not installed」 |
| ⚠ 事实登记 | Step 4 构建曾在源树留下 `src/experiment_doctor.egg-info/`，使上述 skip 变为 pass（一次跑出 `213 passed`，非 212+1）。已删除 `src/experiment_doctor.egg-info/` 与 `build/` 并重跑：skip 恢复、ruff/format/mypy 复绿。**代码零改动**，213 与 212+1 之差完全由该构建残留解释 |
| **TODO** | CI（`.github/workflows/ci.yml`）跑 `pip install -e ".[dev]"` + 同一套门禁，会在 CI 里安装发行物 → packaging 测试在 CI 中不 skip。这属既有行为，无需改动，仅登记 |

## 5. Documentation

| 状态 | 事实 |
|---|---|
| DONE | `docs/rules/ED001..ED010.md` 十份契约在册（10/10）；`docs/reported_summary_schema.md`、`docs/schema/environment-provenance.md` 在册 |
| DONE | 设计文档齐备：`EXPERIMENT_DOCTOR_V1_DESIGN.md`、`EXPERIMENT_DOCTOR_V1_IMPLEMENTATION_PLAN.md`、`PHASE1..PHASE5` 五份阶段报告 |
| **TODO** | **路径事实**：`docs/v1_design/` 位于 `<parent>/docs/v1_design/`（仓库根同级），在**仓库根之外**，`git ls-files docs/v1_design` 为空、`git check-ignore` 亦不忽略 → 该目录**当前无法被任何 commit 收录**。要么移入库内 `v0.1/docs/`，要么显式接受"设计文档不随包发布"（人工决策，本轮不动文件） |
| **TODO** | `README.md` 未覆盖 v1：只文档化 `scan/audit/rules/adapters` 四命令，缺 `init/run/verify`、缺 capture-first 链路、缺 `captured` adapter；且 `## Limitations` 的"Read-only auditor: it never re-runs training"与 `## Output` 的"Nothing is ever written into the audited project"两句对 v1 的 `run`/`init` **不再全局成立**（对 audit 仍成立）。审计细节见 `V1_RELEASE_CANDIDATE_REPORT.md` §5 |
| **TODO** | `CHANGELOG.md` 只有 `## v0.1.0`，无 v1.0 条目 |
| **TODO** | `docs/PROJECT_STATE.md` 仍以 v0.1 为当前状态描述（其 §15 含本地绝对路径，属既有已发布内容） |
| DONE | 营销化检查：README/CHANGELOG/包 docstring **不含** "AI agent / 自动实验优化 / 模型提升 / 可信度评分 / overall score / confidence score" 类表述；README 反而明文声明 "There is deliberately no composite trust score and no overall verdict"（与 v1 禁令一致，无需删除） |

## 6. Security scan

| 状态 | 事实 |
|---|---|
| DONE | 凭据扫描：对 `src/experiment_doctor/ scripts tests README.md` grep `password\|passwd\|secret\|token\|credential\|api_key` → 命中项全部为既有 v0.1 代码里的**同名局部变量/正则词**（`generic.py` 前缀 token、`gmmvi.py` id token、`run_rule_acceptance.py` 的 `HARDCODE_TOKENS`）与测试 docstring 里的叙述；**无任何凭据读写逻辑** |
| DONE | 本地用户名扫描：`grep -rl "<本机用户名>" src scripts tests README.md pyproject.toml docs` → **0 命中** |
| DONE | 绝对路径扫描（将进入发布面的文件）：`src/experiment_doctor/**.py`、`scripts/run_v1_*.py`、`tests/test_v1_*.py`、`tests/fixtures/v1_*`、`README.md`、`pyproject.toml`、`docs/` → v1 新增文件 **0 命中**；命中者为既有内容：`docs/PROJECT_STATE.md:15`、`scripts/run_rule_acceptance.py:7-11`（文档串里的验收命令行示例）、仓库根 `rule_acceptance.json`（**tracked**，含 `<parent>/...` 与 `<repo>/src/...` 形式的本机绝对路径，v0.1 已于 `b691752` 提交并随 0.1.0 发布） |
| DONE | v1 运行期不产生硬编码路径：路径全部来自 CLI 参数 / `Path.resolve()`；`scripts/run_v1_full_pipeline_check.py` 默认输出到相对 `tmp/p5`（`--work/-o` 可改，`tmp/` 已 gitignore） |
| DONE | 网络/上传/压缩/签名：v1 import 面无 `urllib/requests/http*/socket/zipfile/tarfile/gzip/make_archive/sign` 任何一项；grep 命中仅注释文本（`runner.py:338` "no upload, no signing"） |
| DONE | 边界（Phase 5 Step 5 实测，本轮沿用）：环境变量蜜罐 `ED_CANARY_PASSWORD` 不出现在 bundle 任何文件；`run` 前后项目外文件集合逐字节不变；`.git/logs/HEAD` 与 HEAD 字节不变；对外部真实仓库（CRDA/TorchSSL clone）审计后 `find -newer` 计数 0、`git status --porcelain` 0 行 |
| **TODO** | 是否把 3 项既有绝对路径（`rule_acceptance.json`、`PROJECT_STATE.md:15`、`run_rule_acceptance.py:7-11`）从公开仓库剥离，属**人工决策**：它们是 v0.1 已发布内容，清理=改写既有 tracked 文件（本轮"只报告事实，不修改"） |

## 7. Known limitations（v1.0 MVP 已知边界，登记不修复）

| 状态 | 事实 |
|---|---|
| DONE 已登记 | 详细 10 条见 `PHASE5_FINAL_VALIDATION_REPORT.md` §8；各阶段"诚实清单"见 PHASE1 §5.4、PHASE2 §6、PHASE3、PHASE4 §8。要点：|
| | ① lock 内 `execution.start_time` 保持 UNKNOWN（run 观测不回填 lock）；② 无 budget 块（GMMVI `sed` 注入预算仍不可恢复）；③ 不从 stdout 提取 metric、无 metric 字段；④ 被删文件只进 `artifacts.note`，schema 无结构化字段；⑤ Unix 信号退出码在 CLI 层降级为 1（record 保真）；⑥ timeout 后 kill 未确认时 exit_code=UNKNOWN；⑦ `resolved_config`/dataset version/method 等六类字段刻意不映射（宁 UNKNOWN 不假 PASS）；⑧ 无 Hydra/MLflow/W&B 集成（v1.1 裁决）；⑨ 空项目 0 条规则结果（不是 UNKNOWN）；⑩ `COVERAGE_FIELDS` 未含 `runtime_environment` 子字段（冻结列表，驱动改读 project dump） |
| **TODO** | 以上任何一条若要转为功能，需另立任务书（v1.1 或 patch），本轮"不扩展功能" |

## 8. Rollback point

| 状态 | 事实 |
|---|---|
| DONE | 回滚锚点 = **HEAD `e17ab18cf087e1410259f110150fa16d49429373`**，且 `origin/master` 与之 **0/0 完全一致** → 远端公开状态 = v0.1.0 已发布状态，**v1 全部工作只存在于本地未提交文件** |
| DONE | 回滚动作（无需改写历史）：丢弃 3 个 M（`git checkout -- src/experiment_doctor/adapters/__init__.py src/experiment_doctor/cli.py tests/test_packaging.py`）+ 删除 12 条 untracked 路径，即回到与远端逐字节一致的 v0.1.0 |
| DONE | 已发布不可变锚点：tag `v0.1.0` → `7c9e550…`；PyPI `experiment-doctor 0.1.0`（既有事实，本轮未触碰） |
| **TODO** | 一旦按建议 commit（本轮**未执行**），回滚点即从"丢弃未跟踪文件"变为"需要 revert/reset"，因此三个建议 commit 应先在人工确认后再落地 |

---

## 汇总

| 分区 | DONE | TODO |
|---|---|---|
| 1 Version | 3 | 2 |
| 2 Package metadata | 5 | 1 |
| 3 CLI | 4 | 2 |
| 4 Tests | 5（+1 ⚠ 事实登记） | 1 |
| 5 Documentation | 2 | 4 |
| 6 Security scan | 6 | 1 |
| 7 Known limitations | 1（10 条已登记） | 1 |
| 8 Rollback point | 3 | 1 |
| **合计** | **29** | **13** |

**结论（不含发布动作）**：代码/测试/安全/回滚四区 DONE；TODO 集中在**版本号提升、发行文案、README/CHANGELOG 文档补写、设计文档的仓库归属路径**，全部属人工决策项，本轮按任务书"不是开发阶段，不增加功能、不发布"未执行任何 commit/push/tag/PyPI 动作。
