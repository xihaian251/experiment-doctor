# Experiment Doctor v1.0 — 最终发布报告（RC Final Decision & Release Preparation）

- 日期：2026-09-27
- 阶段：RC Final Decision。允许：版本决策落地（两个版本常量 + CHANGELOG）、门禁复跑、wheel/sdist 双干净安装复验、生成本报告。禁止：扩展功能、改 schema/rules/audit/scanner/adapter、push、tag、GitHub Release、PyPI publish
- 上一份：`docs/v1/V1_RELEASE_CANDIDATE_RC2_REPORT.md`（RC2）；台账：`docs/v1/V1_RELEASE_CHECKLIST.md`
- 本轮结束状态：**版本号已落地为 `1.0.0`（commit `717e3cf`）；工作树 clean；未 push、未 tag、未发布**。本文件随后作为一笔 `docs:` commit 入库（其 sha 由 `git log -1` 读取，本文件不预测自身身份）
- 记法：`<repo>` = 本仓库 git toplevel；`<parent>/` = 仓库根的同级目录；`<本机用户名>` = 本机账户名

---

## 1. RC2 blocker 处置结果

| # | RC1/RC2 登记项 | RC2 结束时 | 本轮（Final） | 证据 |
|---|---|---|---|---|
| B1 | v1 工作未提交 | 已解决（三笔 A/B/C） | 保持；另加 3 笔文档/版本 commit | `git log --oneline e17ab18..HEAD` 共 6 行（§3） |
| B2 | 文档在仓库外 | 已解决（迁入 `docs/v1/`） | 保持，本轮无迁移动作 | `git ls-files docs/v1` = 11 份 .md（含本文件后为 12） |
| **B3** | **版本号仍为 `0.1.0`** | 按任务书保持未决 | **已解决** — 人工确认取 `1.0.0`，Step 2 落地（§2） | `git show 717e3cf --stat`；`src/experiment_doctor/__init__.py:28`、`tests/test_packaging.py:27` |
| B4 | README/CHANGELOG 不描述 v1 | 已解决 | 保持；CHANGELOG 的 `Unreleased` 段改写为带日期的 `## v1.0.0 — 2026-09-27` | `git show 717e3cf -- CHANGELOG.md` |
| B5 | 绝对路径是否阻断发布 | 已分类（判定不阻断） | 保持。本轮对 `1.0.0` 的两个产物重做逐成员字节扫描，命中 **0**（§5.4） | 三个模式串（父目录名 / 用户目录前缀 / 本机用户名），见 §5.4 |
| D2（RC2 §8） | `pyproject.toml description` 与包 docstring 仍写 "Read-only …" | 未决 | **人工确认：本轮不动**，登记为已知不一致（§6 L9） | `git diff 827071e..HEAD -- pyproject.toml` 为空 |

Step 0 复核（本轮开始前，未改代码）：`git diff --name-status e17ab18..HEAD -- src/experiment_doctor` 相对 v0.1 发布线只有 `A`×16（`v1/**` 15 + `adapters/captured.py`）+ `M`×2（`adapters/__init__.py`、`cli.py`）；`rules/`、`schema.py`、`audit.py`、`scanner.py`、`provenance.py` 与四个验收 adapter 均为 **0 改动**。`schema_version` 三处常量均为 `"1.0"`（`v1/lock/schema.py:24`、`v1/run/schema.py:26`、`v1/verify/schema.py:20`），并被 `tests/test_v1_lock_capture.py:247`、`tests/test_v1_run_capture.py:309` 锁定。CLI 公开面为 7 个命令（`scan audit rules adapters init run verify`），由 `tests/test_v1_verify.py:332` 逐命令 `--help` 锁定。release-blocking issue：无。

## 2. 版本决策

**推荐并已由人工确认：`1.0.0`。**

理由（四条，均可验证）：

1. **无破坏性变更**：v0.1.0 发布点 `e17ab18` 之后，冻结面（rules / schema / audit / scanner / provenance / 四个验收 adapter）逐字节未动；v0.1 legacy 测试 118+1 零漂移；三个真实项目的验收 JSON 与历史基线 sha256 全等。PEP 440 / SemVer 语义下这是 minor 级加法，而 0.x → 1.0 的跨越本身不携带"破坏"含义。
2. **契约已内部记为 1.0**：lock / run / verify 三类证据记录的 `schema_version` 常量就是 `"1.0"`。包版本取 `0.2.0` 会让日志里出现"记录 1.0 / 工具 0.2"的双编号；取 `1.0.0` 使两套编号合一。
3. **命令面与 JSON 面已冻结**：7 命令集合、`report.json` 结构、evidence bundle 四件套均有测试锁定；本轮又用 wheel 与 sdist 两个独立安装副本复跑通过（§5.3）。这正是"公开接口"的操作性定义。
4. **里程碑命名一致**：`EXPERIMENT_DOCTOR_V1_IMPLEMENTATION_PLAN.md` 自始称本轮为 **v1.0 MVP**；若先发 `0.2.0`，该里程碑在版本史上将没有对应物。

SemVer 解释：SemVer §4 规定 major 为 0 时 API 不必稳定、任何改动可视为破坏性；§7 规定 1.0.0 定义稳定公共 API。取 `1.0.0` 即宣布 CLI 与 JSON 契约进入公开稳定期，此后破坏性变更须升 major。已知限制（§6）因此成为该承诺的边界说明，而非未列出的隐含风险。

落地动作（Step 2，严格限于任务书授权的三个文件）：

| 文件 | 改动 |
|---|---|
| `src/experiment_doctor/__init__.py` | `__version__ = "0.1.0"` → `"1.0.0"`（唯一版本来源） |
| `tests/test_packaging.py` | `RELEASE_VERSION = "0.1.0"` → `"1.0.0"`（第二锁）+ 模块 docstring 首行版本字样 |
| `CHANGELOG.md` | `## Unreleased — v1 capture pipeline (release candidate, not published)` → `## v1.0.0 — 2026-09-27`；正文补一句"发布决策已记录，分发物尚未上传" |

单一来源不变式保持：`pyproject.toml` 仍是 `dynamic = ["version"]` + `version = { attr = "experiment_doctor.__version__" }`，本轮 **未改 `pyproject.toml` 一个字节**。README 无 version badge（全文核实），故任务书"若存在"一项为 no-op。schema / rules / audit / scanner / adapter 未触及。

## 3. Commit 历史

截至版本落地这一笔（本报告自身的入库 commit 在其后，故此处不预测自己的 sha）：

```
717e3cf chore: set release version 1.0.0                       ← 本轮（B3 关闭）
827071e docs: clarify scan-pattern wording in the RC2 report   ← RC2 收尾
02db843 docs: record RC2 resolution report                     ← RC2 收尾
a3b8b82 docs: finalize v1 MVP documentation                    ← Commit C
45048fe test: add v1 end-to-end validation                     ← Commit B
dfdd19b feat: add experiment capture and verification pipeline ← Commit A
e17ab18 docs: record published 0.1.0                           ← origin/master / v0.1.0 线
```

| Commit | 内容 | 体量 |
|---|---|---|
| A `feat` | `src/experiment_doctor/v1/**` 15 个 .py、`adapters/captured.py`、adapter 注册、CLI 接线 | 18 files +2054/−5 |
| B `test` | 4 个 `tests/test_v1_*.py`、5 个 fixture 目录、`scripts/run_v1_full_pipeline_check.py` | 17 files +1893/−1 |
| C `docs` | `docs/v1/` 9 份 + README + CHANGELOG | 11 files +1903/−6 |
| RC2 报告 2 笔 | `V1_RELEASE_CANDIDATE_RC2_REPORT.md` 入库（+162）与其扫描模式措辞澄清（+2） | 1+1 files |
| 本轮 `chore` | 版本常量 ×2 + CHANGELOG 段标题 | 3 files +6/−5 |
| 合计至 `717e3cf` | 相对 `e17ab18`：`git diff --shortstat e17ab18..717e3cf` | **48 files, +6018/−15**；`git rev-list --left-right --count origin/master...HEAD` = `0 6` |

自 `e17ab18` 起，v1 全部工作共 6 笔（后为 7 笔，含本文件），**未 push 计数由 `git rev-list` 现场读取**（本文件不预测自身入库后的数字）。已有 tag 仅 `v0.1.0`（→ `7c9e550`），本轮**未新增 tag**，`git tag --list` 输出仍只有该一行。

## 4. Package 产物（发布决策所需的哈希）

构建自提交后的树（工作树内容 == `717e3cf`）；`python -m build --no-isolation`。

| 产物 | 字节 | sha256 |
|---|---|---|
| `dist/experiment_doctor-1.0.0-py3-none-any.whl` | 132,806 | `686226b2350f0b5d615e31a96a5434f8cf0a6e03fc3316d5ae103f68a63caeae` |
| `dist/experiment_doctor-1.0.0.tar.gz` | 147,125 | `24731c8e05fb6921ae298d2a837ffe451341ff86f7ec78dbd529e6272176d3c6` |

- wheel：48 条目 / 42 个 .py；顶层目录 `experiment_doctor/`、`experiment_doctor-1.0.0.dist-info/`；`METADATA` 首行为 `Metadata-Version / Name: experiment-doctor / Version: 1.0.0`。
- sdist：78 条目（其中 66 个文件），顶层 `src/`、`tests/` + `LICENSE PKG-INFO README.md pyproject.toml setup.cfg`；**不含** `docs/`、`scripts/`（无 MANIFEST.in）。
- 元数据其余面：`requires-python >=3.11`；依赖 `pydantic>=2.5 typer>=0.12 PyYAML>=6.0`；入口点 `experiment-doctor = experiment_doctor.cli:main`；license Apache-2.0；`Summary` 仍是 v0.1 的 "Read-only …"（§6 L9）。
- 与 v0.1.0 产物对比：wheel 由 131,418 → 132,806 字节（+`v1/**` 与 `captured.py`）；旧哈希 `4798a4a9…` 已失效，正式发布须以上表（或发布当次重建）的哈希为准并登记。

**可复现性事实**：不加环境变量的两次构建，wheel 与 sdist 哈希**均不同**（归档时间戳入包）。固定 `SOURCE_DATE_EPOCH` 后连建两次：wheel 两次全等（`686226b2…`，**可复现**），sdist 仍不等（`19c3ff…` vs 上表 `24731c8e…`，成员顺序/时间元数据未被完全钉住）。因此 §4 的 sdist 哈希只标识"本次构建的这一份"，正式发布须在发布当次构建、当场记哈希（v0.1 即按此执行）。

## 5. 验证结果

### 5.1 本地四门（版本改动后）

| 门禁 | 结果 |
|---|---|
| `pytest -q` | **212 passed, 1 skipped**（215.55s；v0.1 legacy 118+1 零漂移 + v1 94） |
| `ruff check .` | All checks passed! |
| `ruff format --check .` | 93 files already formatted |
| `mypy src scripts tests` | Success: no issues found in 64 source files |
| 唯一 skip | `tests/test_packaging.py:48`（源树运行、发行物未安装）— 环境性跳过，非失败 |

### 5.2 边界自查

- `git diff --name-only -- rules/ schema.py audit.py scanner.py provenance.py adapters/{gmmvi,torchssl,crda,generic}.py v1/ pyproject.toml README.md` → **0 行**（本轮改动面 = 版本常量两处 + CHANGELOG）。
- 每次构建后 `rm -rf build src/experiment_doctor.egg-info`，否则 `PYTHONPATH=src` 下 `importlib.metadata.version()` 会成功、使 :48 的 skip 静默变 pass（假 "213 passed"）。本轮三次构建后均已清理，`git status --short` 回到只有那 3 个（提交后为 0 行）。

### 5.3 双干净安装复验（wheel 一个 venv，sdist 另一个 venv）

两个临时 venv（`tmp/whl_venv`、`tmp/sdist_venv`），均 `pip install --no-deps` 对应产物；`import experiment_doctor` 分别解析到各自 `Lib/site-packages/...`（非 editable），`__version__` 均为 **1.0.0**。在仓库外两个同构 demo 目录（`train.py` + `config.yaml`）各跑完整链路，四步退出码全 0：

| 步骤 | wheel 安装副本 | sdist 安装副本 |
|---|---|---|
| `init --seed 7 --config config.yaml`（**故意不给 `--command`**） | `lock_hash sha256:06ee7a56…`；`randomness.seed=CONFIRMED` / `execution.command=UNKNOWN` | `lock_hash sha256:1db3cb75…`；同一字段向量 |
| `run -- python train.py --seed 7` | `run_hash sha256:0d9653cf…`；`lock_reference` 与 lock 一致；`termination: SUCCESS`；`execution.command=CONFIRMED`；`artifacts.created_files=CONFIRMED` | `run_hash sha256:f3e185c3…`；同一字段向量 |
| `verify` | V001–V006 全 PASS，退出 0 | V001–V006 全 PASS，退出 0 |
| `audit . -o out` | `adapter=captured families=1 runs=1 rules=6 fail=0 inconclusive=2` | 同一行 |
| 规则向量 | `ED001 NOT_APPLICABLE / ED002 PASS / ED003 PASS / ED004 INCONCLUSIVE / ED009 INCONCLUSIVE / ED010 PASS` | 与 wheel **逐项相同**（脚本比对 `dict ==` 为 True） |
| `adapters` | 5 个在册，`captured` 描述与 Phase 4 契约一致（不产 metric、不宣告实验结果、不升级 provenance） | 同 |

两次 `pytest tests/test_packaging.py`（在两个安装副本环境中）均 **6 passed**，其中包含 :48 的"已安装元数据版本 == `__version__`"这一在源树中被跳过的锁 → `1.0.0 == 1.0.0` 成立。

内容等价性：当前 wheel 内 `experiment_doctor/__init__.py` 的 sha256（`60b4c141…`）与两个 venv 已安装副本逐字节相同 → §5.3 的行为证据适用于 §4 登记的产物内容。

附带的一条负向证据：初次 demo 脚本自身有语法错误，`run` 如实记录 `termination: FAILED` 且退出码 1，`verify` 仍 V001–V006 全 PASS —— 失败被记录而非被推断，工具不因实验失败而误报自身故障。

### 5.4 发布边界扫描（`1.0.0` 产物）

> 术语澄清：本小节的扫描模式一律以占位符书写，正文中**不出现**完整的本机绝对路径或本机用户名；"命中 0"专指盘符路径与用户名这两类字节序列。

对 wheel 48 个成员、sdist 66 个文件成员做字节级匹配（三个模式串：仓库父目录名、`C:\<用户目录>` 前缀、`<本机用户名>` UTF-8 字节）：**命中 0**。仓库内 4 组既有本机绝对路径（`rule_acceptance.json`、`scripts/run_rule_acceptance.py`、`docs/PROJECT_STATE.md`、两份 v0.1 根级报告）仍在，但三者均不在发行载荷内 → 维持 RC2 的"仅历史记录、不阻断发布"判定（清理=改写 v0.1 已发布文件，需人工单独授权）。

### 5.5 真实项目

按任务书**未重跑** GMMVI / TorchSSL / CRDA。沿用既有黄金证据 21/21、46/46、25/25、19/19，四份输出与 Phase 4 基线 sha256 全等（`23fff61805… / a2282b9a44… / 1f4bedaa1b… / 199462cbf6…`）。

## 6. 已知限制

| # | 限制 | 性质 |
|---|---|---|
| L1 | 不做 metric 提取：stdout/stderr 只作为日志保存，从不解析；无自动推断指标 | 设计约束（两扇门纪律） |
| L2 | 不宣告训练结论：`SUCCESS` 仅表示进程退出 0；无质量/收敛含义 | 设计约束 |
| L3 | 无 composite / confidence / trust score；规则逐条给状态，聚合层只有计数 | 设计约束 |
| L4 | capture 是 forward-only：对从未捕获的历史归档无能为力，只能走 v0.1 只读审计 | 能力边界 |
| L5 | 未捕获 hardware / cuda / GPU 拓扑；无 budget 块；删除文件只进 `artifacts.note` 而非结构化字段 | 未实现（属 v1.1 候选） |
| L6 | 无 Hydra / MLflow / W&B / tracker 集成；`dataset.paths` 未声明即 UNKNOWN | 未实现 |
| L7 | `run` 会真实执行 `--` 之后的命令；`init`/`run` 在项目根写自身证据文件（审计侧 `scan/audit/rules/adapters` 仍完全只读） | 使用须知 |
| L8 | sdist 不可字节复现（§4）；正式发布须发布当次构建并当场记哈希 | 工具链事实 |
| L9 | 三处 v0.1 措辞与实际能力不一致：`pyproject.toml description`（随 `METADATA` 发布，PyPI 首页可见）、包 docstring（`The tool never writes into the audited project`）、`cli.py` 顶层帮助文本 `Experiment Doctor v0.1: …` 与两处命令 docstring 的 "v0.1"。均属文案而非代码语义；Step 2 授权面仅"两个版本常量 + CHANGELOG"，人工决定本轮不动 | 元数据/帮助文案待办 |
| L10 | 仓库内 4 组既有本机绝对路径（仅历史记录，不在载荷内）；公开仓库可见目录布局 | 需单独授权才可清 |
| L11 | 尚无 `v1.0.0` tag、未 push、未发布；`.github/workflows/publish-pypi.yml` 未触发 | 状态，非缺陷 |

## 7. 发布就绪判断与待授权动作

**判断：v1.0.0 已处于可发布状态（release-ready），但本轮未执行任何发布动作。** 依据：版本决策已落地（§2）、四门全绿（§5.1）、冻结面零改动（§5.2）、wheel 与 sdist 两个独立安装副本全链路复验通过且规则向量一致（§5.3）、载荷内本机路径与凭据零命中（§5.4）。

若要正式发布，需人工按顺序授权以下步骤（本轮**全部未做**）：

1. `git push` 6 笔 commit（触发 GitHub CI：`pip install -e ".[dev]"` + 同四门）；
2. 决定 tag 名：`v1.0.0`（若跳过计划原预留的 `v1.0.0-alpha.1`），tag 指向 `717e3cf`；
3. 发布当次重建产物、当场记录 sha256（§4 的 sdist 复现性事实）；
4. 若同时处理 L9（`description` / 包 docstring / `cli.py` 帮助文案），须与 D2 一并作为独立小 commit，并在四门后重建；
5. GitHub Release + PyPI publish（v0.1 走 Trusted Publishing，由 tag 触发的 workflow 完成）。

---

*RC Final 终点：B3 关闭，版本 `1.0.0` 落地于本地第 6 笔 commit `717e3cf`，工作树 clean；未 push、未 tag、未 GitHub Release、未 PyPI 发布、未进入 v1.1。*
