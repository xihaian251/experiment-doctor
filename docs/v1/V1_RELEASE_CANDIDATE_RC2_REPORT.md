# Experiment Doctor v1.0 — RC2 报告（RC Resolution 阶段）

- 日期：2026-09-27
- 阶段：RC Resolution（解决 RC1 登记的 blocker）。允许：整理提交结构、移入文档、更新版本元数据、更新 README/CHANGELOG、清理发布边界。禁止：新增功能、改 ED001–ED010、改 schema、改 audit pipeline、改 adapter 语义、新增 Phase、扩展 v1.1
- 上一份：`V1_RELEASE_CANDIDATE_REPORT.md`（RC1）；台账：`V1_RELEASE_CHECKLIST.md`
- 本轮结束状态：**三笔本地 commit，工作树 clean，未 push、未 tag、未发布**；版本号**未**改动（Step 3 要求先等人工确认）
- 记法：`<repo>` = 本仓库 git toplevel；`<parent>/` = 仓库根的同级目录
- 状态更新（RC Final，同日）：本文件为 **RC2 时点快照**。文中"三笔 commit / 版本号未改动 / §8 D1、D2 待决"已过时：版本决策定为 `1.0.0` 并落地于本地第 6 笔 commit `717e3cf`，D2（`description` 文案）确认本轮不动；后续事实以 `V1_RELEASE_FINAL_REPORT.md` 为准。

---

## 1. Blocker 处置结果

| # | RC1 登记的 blocker | 处置 | 证据 |
|---|---|---|---|
| **B1** | v1 工作未提交（3 M + 12 untracked，远端仍是纯 v0.1.0） | **已解决** — 按 §2 的划分落为三笔本地 commit | `git log --oneline -4`；`git status --short` 输出 0 行；`git rev-list --left-right --count origin/master...HEAD` = `0 3`（本地领先 3，未推送） |
| **B2** | `docs/v1_design/` 在仓库根之外，"docs" commit 落不进去 | **已解决** — 9 份文档迁入仓库内 `docs/v1/`，随 commit C 入库；`docs/v1_design/` 空目录已移除 | `git show --stat a3b8b82` 列 `docs/v1/*.md` 共 11 文件（含 README/CHANGELOG）；迁移后 `ls ../docs` 仅剩验收目录 |
| **B3** | 版本号仍为 `0.1.0` | **按任务书保持未决** — Step 3 明确"先不要自动修改、不要直接 bump"，故 `pyproject.toml` 与 `__init__.py` 逐字节未动（`git diff e17ab18..HEAD -- pyproject.toml` 为空）。决策依据见 §3 | 三笔 commit 均未触及 `pyproject.toml` / `src/experiment_doctor/__init__.py` |
| **B4** | README/CHANGELOG 不描述 v1 | **已解决** — README 增 4 处、CHANGELOG 增 `## Unreleased — v1 capture pipeline` 段，细节见 §4 | `git show a3b8b82 --stat`：README +76/−6、CHANGELOG +25 |
| **B5** | 既有绝对路径需判断是否影响发布 | **已分类解决**（判定为不阻断，未删除历史证据），见 §5 | sdist/wheel 逐成员字节扫描：本机路径与用户名命中 **0** |

新增的越界自查（本轮实际改动是否越过禁止项）：

| 禁止项 | 复核 |
|---|---|
| 改 ED001–ED010 / schema / audit pipeline / adapter 语义 | `git diff --name-only e17ab18..HEAD -- src/experiment_doctor/rules src/experiment_doctor/schema.py src/experiment_doctor/audit.py src/experiment_doctor/scanner.py src/experiment_doctor/provenance.py adapters/{gmmvi,torchssl,crda,generic}.py` → **空** |
| 新增功能 | 三笔 commit 全部落在 Phase 1–5 已交付文件 + 文档/元数据文案；`v1/**` 与 `captured.py` 的实质代码未改，唯一源码改动是 3 处 docstring 里的文档路径字面量（`docs/v1_design/` → `docs/v1/`） |
| 新增 Phase / 扩展 v1.1 | 未做 tracker 集成、budget 块、metric 字段、结构化 deleted 文件 |
| 发布动作 | 未 push、未 tag、未 build 上传；build 仅在本地产物后用于扫描并已删除 |

## 2. Commit 结构

```
a3b8b82 docs: finalize v1 MVP documentation          ← Commit C
45048fe test: add v1 end-to-end validation           ← Commit B
dfdd19b feat: add experiment capture and verification pipeline   ← Commit A
e17ab18 docs: record published 0.1.0                 ← 远端 / v0.1.0 发布线
```

| Commit | 内容 | 体量 |
|---|---|---|
| A `feat` | `src/experiment_doctor/v1/**` 15 个 .py（capture/lock/run/verify/cli）、`adapters/captured.py`、`adapters/__init__.py` 注册、`cli.py` 接线 | 18 files, +2054/−5 |
| B `test` | 4 个 `tests/test_v1_*.py`、5 个 `tests/fixtures/v1_*`、`scripts/run_v1_full_pipeline_check.py`、`tests/test_packaging.py` 的 adapter 集合 | 17 files, +1893/−1 |
| C `docs` | `docs/v1/` 9 份（设计 2 + 阶段报告 5 + 清单 + RC1 报告）、`README.md`、`CHANGELOG.md` | 11 files, +1903/−6 |
| 合计 | 相对 v0.1.0 发布点 `e17ab18` | **46 files, +5850/−12** |

提交纪律：每笔前 `git diff --cached --stat` 已核对；三笔后 `git status --short` 为空；`.pyc`/`__pycache__` 未进入任何 commit（`.gitignore` 生效，A 的 18 个文件全是 .py）；`tmp/` 未入库。

### 2.1 文档迁移的可追踪性

- 迁移前 `../docs/v1_design/*.md` **从未被 git 跟踪**（`git ls-files` 为空），因此不存在 `git mv` 的历史可保；这些内容的 git 历史自 `a3b8b82` 起算，此前不存在。该事实如实登记，不假称"rename 保留历史"。
- 内容层面的改动只有两类：① 路径自引用（`EXPERIMENT_DOCTOR_V1_IMPLEMENTATION_PLAN.md` 头部指向 `docs/v1/EXPERIMENT_DOCTOR_V1_DESIGN.md`）；② 本机绝对路径 → `<repo>` / `<parent>/` 占位符、用户名 → `<本机用户名>`。**没有改写任何数字、判定或结论**（任务书：禁止修改报告事实内容）。
- 两份 RC 文档头部各加一行「状态更新（RC Resolution）」指向本文件，避免读者按已过期的 TODO 行动。

## 3. 版本决策（未执行 bump，待人工确认）

现状事实：`src/experiment_doctor/__init__.py` `__version__ = "0.1.0"`；`pyproject.toml` 走 `dynamic = ["version"]` 单一来源；`tests/test_packaging.py:27 RELEASE_VERSION = "0.1.0"` 与之一同被测试锁定 → **升版本必须同改两处**，改一处必红。已发布：tag `v0.1.0` → `7c9e550`、PyPI `experiment-doctor==0.1.0`。

| 维度 | Option A：`1.0.0` | Option B：`0.2.0` |
|---|---|---|
| 与既有制品的关系 | v0.1.0 之后**无任何破坏性变更**：冻结面 diff 为空、v0.1 legacy 118+1 零漂移、三项目验收 JSON 与基线 sha256 全等 | 同一事实下，"纯加法的新功能"正是 semver 对 0.x 段 minor bump 的定义 |
| 与内部契约的一致性 | 证据记录本身已写 `schema_version = "1.0"`（lock/run/verify 三处常量），包版本 1.0.0 与之对齐，读日志的人不会看到"记录 1.0 / 工具 0.2"的错位 | 包版本与记录 schema_version 分离，需在文档解释两套编号 |
| 与既有计划的吻合度 | `EXPERIMENT_DOCTOR_V1_IMPLEMENTATION_PLAN.md` 自始把本轮称为 **v1.0 MVP**，且计划原文在 Phase 5 末预留的是 `v1.0.0-alpha.1`（仅仓库 tag 线，不发布） | 与计划命名不一致 |
| 对使用者的承诺强度 | "1.0" 暗示 CLI 与 JSON 契约进入公开稳定期，后续破坏性变更需 major；当前已知限制清单（10 条）会成为该承诺的一部分 | 明示"仍在 0.x，接口仍可能变动"，与 tracker 集成、budget 块等待裁决项并存更保守 |
| 风险 | 抬高预期：Hydra/MLflow/W&B 未集成、无 hardware/cuda 捕获、删除文件只进 note | 无技术风险；但 `0.2.0` 之后再发 `1.0.0` 会让"v1.0 MVP"这个里程碑在版本史上失去对应物 |

**建议（不执行）**：若本轮即宣告 MVP 完成并对外承诺 CLI/JSON 契约，取 **`1.0.0`**；若把 tracker 集成 / v1.1 裁决视为破坏性变更的前置期，取 **`0.2.0`** 并在 `docs/v1/` 记一句"schema_version 与包版本两套编号"。两者落地动作相同：同改 `__init__.py` 与 `tests/test_packaging.py:RELEASE_VERSION`，跑四门，然后才谈 tag/publish。**本轮一个字都没改。**

## 4. README / CHANGELOG 修订（Commit C）

README 新增或改写的段落：

| 位置 | 内容 |
|---|---|
| 副标题 | 由「Read-only provenance and aggregation audit」改为「Provenance audit … plus capture-first evidence collection」，并立即限定：审计侧（`scan/audit/rules/adapters`）只读，捕获侧（`init/run/verify`）记录你自己运行的实验 |
| Quick start | 拆成两块：审计既有产物（4 命令原样）+ 运行时捕获（`init --seed 42 --config config.yaml` → `run -- python train.py --seed 42` → `verify` → `audit`） |
| **## Capture-first pipeline**（新） | lock→bundle→verify→captured adapter 的流程图与各自记录什么；**UNKNOWN discipline 明示为两条规则**：① Two doors（只有直接观测与显式声明两扇门，没有第三道；未给 `--seed` 则 lock 保持 UNKNOWN，即便 config 里写着 seed）；② No outcome claims（`SUCCESS` 只表示进程退出 0，不表示训练质量；stdout/stderr 只作为日志保存，从不解析 metric；无任何 composite/confidence score）；并注明 `run` 会执行 `--` 之后的命令、`init/run` 只在项目根写自身证据文件 |
| Adapters | 补 `captured` 条目（读 bundle；bundle 在场且完好时被自动选中；引用搬家到 bundle 文件以满足 attached_to_run） |
| Output / Limitations | 把"Nothing is ever written into the audited project"限定到审计路径；补"`run` 不自行发起训练""capture 是 forward-only（对从未捕获的归档无能为力）" |
| Development / validation | 点名 `scripts/run_v1_full_pipeline_check.py`（四树驱动、状态向量必须重复一致）与 `docs/v1/` 索引 |

禁用词自查：新增文案不含 AI / agent / automatic improvement / 自动实验优化 / 模型提升 / trust score / overall score；出现的 "no composite or confidence score"、"no outcome claims" 是**否定式承诺**，与既有 README 的 "There is deliberately no composite trust score" 同性质，非营销用语。

CHANGELOG：顶部新增 `## Unreleased — v1 capture pipeline (release candidate, not published)`，逐条列 init / run / verify / captured adapter / 验证规模（94 例 + 驱动）/ **Deliberately absent**（metric 提取、训练结论、budget、tracker 集成、压缩上传签名、composite score）。措辞为 "Unreleased … not published"，与本轮未发布的事实一致；版本决策落定后再改写为带日期的正式段落。

## 5. 绝对路径 / 凭据分类（Step 5）

扫描范围：全仓库（排除 `.git/`、`tmp/`、`__pycache__`、`.mypy_cache`、`.ruff_cache`）匹配 `MLResearch`、`<本机用户名>`、`C:\Users`。

| # | 位置 | 内容 | 分类 | 处置 |
|---|---|---|---|---|
| 1 | `rule_acceptance.json`（tracked，v0.1 `b691752` 引入） | 7 处 `<parent>/experiment-doctor/...` | **B 仅历史记录** | 保留。它是 v0.1 验收证据的一部分，且**不在发行载荷内**（见下方载荷扫描）；删除=销毁历史证据，任务书禁止 |
| 2 | `scripts/run_rule_acceptance.py:7-11` | 4 处（docstring 里的验收命令示例） | **B 仅历史记录** | 保留，同上；不进 sdist/wheel（`scripts/` 不在载荷内） |
| 3 | `docs/PROJECT_STATE.md:15` | 1 处（验收目录位置） | **B 仅历史记录** | 保留；`docs/` 亦不进载荷 |
| 4 | `EXPERIMENT_DOCTOR_V0_1_MVP_REPORT.md`(2) / `EXPERIMENT_DOCTOR_V0_1_RULESET_REPORT.md`(1) | 根级 v0.1 交付报告 | **B 仅历史记录** | 保留（v0.1 已发布事实） |
| 5 | `docs/v1/*.md`（本轮迁入的 9 份） | 迁入前：`F:/MLResearch/...` 共 6 处 + 本机用户名 1 处 | **A 发布相关 → 已修复** | 全部改为 `<repo>` / `<parent>/` / `<本机用户名>` 占位符；迁移后扫描 `git grep --cached` 命中 **0** |
| 6 | `.mypy_cache/`、`.ruff_cache/`、`__pycache__/` 二进制 | 含本机路径与用户名 | **C 不入库** | gitignore 覆盖；不在 commit、不在载荷 |
| 7 | 凭据面（`password/passwd/secret/token/credential/api_key`） | 命中全为 v0.1 既有同名变量/正则词与叙述性 docstring | **C 无凭据** | 无需动作；Phase 2 的 `ED_CANARY_PASSWORD` 蜜罐测试仍绿 |

**发行载荷扫描（分类为 B 的判据）**：本轮本地构建 `experiment_doctor-0.1.0-py3-none-any.whl` 与 `experiment_doctor-0.1.0.tar.gz`，逐成员做字节级匹配（`MLResearch` / `C:\Users` / 本机用户名）：

> 术语澄清：本表把**扫描模式本身**写成了字面量，所以对 `docs/v1/` 复扫时，本文件会命中 4 处「模式声明」文本。这不构成路径泄漏——文中没有出现任何完整的本机绝对路径；表 #5 所说「迁移后命中 0」专指完整的 `<盘符>:\<父目录>\...` 路径字符串与用户名，那两项在迁入的 9 份文档中确为 0。

- wheel：48 条目 / 42 个 .py → 命中 **0**；不含 `docs/`、`scripts/`、`tests/`。
- sdist：78 条目，顶层只有 `LICENSE PKG-INFO README.md pyproject.toml setup.cfg src/ tests/` → 命中 **0**；`docs/` 与 `scripts/` **不在 sdist 内**（无 MANIFEST.in），`tests/` 在内但只含 synthetic fixture。
- 结论：1–4 号项属 **仅历史/仅仓库**，**不阻断发布**；若要连仓库可见性一并清干净，需改写已发布的 v0.1 历史文件（= 事实销毁），故留给人工决策（§6 D3）。构建产生的 `build/`、`src/experiment_doctor.egg-info/` 已删除，工作树回到 clean（否则 `tests/test_packaging.py:48` 的 skip 会静默变 pass）。

## 6. 验证结果

### 6.1 本地门禁（四门，本轮全部在提交前后各跑过）

| 门禁 | 结果 |
|---|---|
| `pytest -q` | **212 passed, 1 skipped**（191.18s；v0.1 legacy 118+1 零漂移 + v1 94） |
| `ruff check .` | All checks passed! |
| `ruff format --check .` | **92 files already formatted**（83 → 92：迁入的 9 份 .md 纳入格式检查，全部已合规） |
| `mypy src scripts tests` | Success: no issues found in 64 source files |
| 唯一 skip | `tests/test_packaging.py:48`（源树运行、发行物未安装）— 环境性跳过，提交后复跑确认仍为 skip |

### 6.2 干净安装复验（从提交后的树）

临时 venv `pip install .` → **非 editable**（site-packages 内 `editable/egg-link/.pth` 标志计数 0；`experiment_doctor.__file__` 解析到 venv 内；`__version__` = 0.1.0）。安装副本在仓库外目录跑完整链路，四步退出码全 0：

| 步骤 | 观测 |
|---|---|
| `init --seed 7 --config config.yaml`（**故意不给 `--command`**） | `lock_hash sha256:0b75cb84…`；`randomness.seed=CONFIRMED`，而 `execution.command=UNKNOWN` ← 两扇门纪律在安装副本上一字不差地复现 |
| `run -- python train.py --seed 7` | `run_hash sha256:1080a886…`；`lock_reference` 与 lock 一致；`termination: SUCCESS`；`execution.command=CONFIRMED`（argv 末两项 `['--seed','7']`）；`artifacts.created_files=CONFIRMED` |
| `verify` | V001–V006 **全 PASS**，退出 0 |
| `audit . -o …` | `adapter=captured families=1 runs=1 rules=6 fail=0 inconclusive=2`，退出 0 |
| `adapters` | 五个 adapter 全部在册，`captured` 描述与 Phase 4 契约一致 |

审计出的 10 规则向量：`ED001 NOT_APPLICABLE / ED002 PASS / ED003 PASS / ED004 INCONCLUSIVE / ED009 INCONCLUSIVE / ED010 PASS` —— 与 `docs/v1/PHASE5_FINAL_VALIDATION_REPORT.md` 黄金向量的 `cap` 逐项相同；`lock` 里 command=UNKNOWN 而 `run` 里 command=CONFIRMED 正是声明/观测分离的活证。

### 6.3 真实项目回归

按任务书**未重跑** GMMVI / TorchSSL / CRDA。沿用既有黄金证据：21/21、46/46、25/25、19/19，四份输出与 Phase 4 基线 sha256 全等（`23fff61805…/a2282b9a44…/1f4bedaa1b…/199462cbf6…`），登记于 `V1_RELEASE_CHECKLIST.md` §4。

## 7. Package 状态（供发布决策）

| 项 | 值 |
|---|---|
| 版本 | `0.1.0`（**未 bump**，Step 3 待确认） |
| 版本来源 | `pyproject.toml dynamic=["version"]` → `experiment_doctor.__version__`；测试第二锁 `tests/test_packaging.py:RELEASE_VERSION` |
| 载荷 | wheel 48 条目 / 42 py（含 `v1/**` 15 + `captured.py`）；sdist 78 条目（`src/ tests/` + 5 个顶层文件）；无 `docs/ scripts/`、无 pycache/json/log/csv、无本机路径 |
| 依赖 | `pydantic>=2.5 typer>=0.12 PyYAML>=6.0`；`requires-python >=3.11`；入口点 `experiment-doctor = experiment_doctor.cli:main`；license Apache-2.0 |
| 命令面 | 7 个：`scan audit rules adapters init run verify` |
| 元数据文案 | `pyproject.toml description` 与包 docstring 仍写 "Read-only …"（v0.1 措辞）。README 已在正文限定，但 **description 属发行元数据，与版本决策同时改最省一次发布** → 归入 §8 |
| CI | `.github/workflows/ci.yml` 未改：`pip install -e ".[dev]"` + 四门，与本轮实测同集合；`publish-pypi.yml` 未触发（未 push） |
| git | 本地 `main` 领先 `origin/master` 3 个 commit；`git status` clean；未 tag |

## 8. 仍待人工决策

| # | 决策 | 现状 / 选项 | 影响 |
|---|---|---|---|
| D1 | **版本**：`1.0.0` 还是 `0.2.0` | §3 两栏依据，本轮未改 | 需同改两处常量；决定 tag 名与 PyPI 上传版本 |
| D2 | `description` / 包 docstring 的 "read-only" 措辞是否随之更新 | 属发行元数据（非代码语义），建议与 D1 同一次改动 | 影响 PyPI 首页陈述，不影响行为 |
| D3 | 是否清掉仓库内 4 组既有 `F:\MLResearch` 路径（#1–#4） | 已判定不阻断发布；清理=改写 v0.1 已发布文件 | 公开仓库可见本机目录布局（不含用户名）；历史证据受损 |
| D4 | 是否 push 三笔 commit / 是否打 `v1.0.0-alpha.1`（计划 §实施顺序原文预留） | 本轮全部未做 | push 会触发 GitHub CI；tag 是发布的 prerequisite |
| D5 | 正式 CHANGELOG 段落（把 `Unreleased` 改为带日期版本） | 依赖 D1 | 发布动作的一部分 |
| D6 | 本 RC2 报告的入库方式 | 已作为 `docs:` commit 落在 §2 三笔之后（若不接受第四笔，可 `git reset --soft HEAD~1` 退回未跟踪状态，纯文档、零风险） | 工作树保持 clean |
| D7 | v1.1 范围（tracker 集成 / budget 块 / 结构化 deleted files / hardware-cuda 捕获） | 全部属新功能，本轮按禁止项未动 | 需另立任务书 |

---

*RC Resolution 终点：B1/B2/B4/B5 已解决，B3（版本）按任务书保持未决；三笔 commit 在本地，`git status` clean；未 push、未 tag、未 PyPI 发布、未进入 v1.1。*
