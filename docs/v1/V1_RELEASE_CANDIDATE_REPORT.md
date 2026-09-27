# Experiment Doctor v1.0 — Release Candidate Report

- 日期：2026-09-27
- 阶段：Release Candidate Preparation 终报（Step 7）
- 定位：把 Phase 1–5 已验证完成的 v1.0 MVP **整理为 RC 状态**。本轮不是开发阶段：未新增功能、未修改代码、未 commit、未 push、未 tag、未发布
- 状态更新（RC Resolution，同日）：本文件为 **RC1 时点快照**，正文事实与数字未改写。其中 B2（文档在仓库外）已通过把 `../docs/v1_design/` 迁入库内 `docs/v1/` 解决、B4（README/CHANGELOG 不描述 v1）已按 D4 补写、B3 版本号**未**改动仍待决策；逐项处置见 `V1_RELEASE_CANDIDATE_RC2_REPORT.md` §1。
- 配套：`V1_RELEASE_CHECKLIST.md`（8 区 DONE/TODO 台账）、`PHASE1..PHASE5_*_REPORT.md`

---

## 1. MVP 最终架构

### 1.1 分层与冻结边界

```
                    ┌─────────────────────────────────────────────┐
  采集侧（v1 新增） │ init ─→ experiment.lock.json                │ Phase 1
                    │ run  ─→ experiment.run.json + 4 文件 bundle │ Phase 2
                    │ verify ─→ V001–V006 + verify.json/md        │ Phase 3
                    └───────────────────┬─────────────────────────┘
                                        │ 只读消费
                    ┌───────────────────▼─────────────────────────┐
  审计侧（v0.1 冻结）│ captured adapter（Phase 4，唯一的 v1→audit 桥）│
                    │ scan → audit → ED001–ED010 → report.json/md  │
                    └─────────────────────────────────────────────┘
```

- **v0.1 核心逐字节未动**：`rules/`（ED001–ED010 + base + severity）、`schema.py`、`audit.py`、`scanner.py`、`provenance.py` 以及 `gmmvi/torchssl/crda/generic` 四个验收 adapter，`git diff` 对 HEAD **为空**；`git diff --quiet -- src/experiment_doctor/rules` 通过。
- v1 与审计侧之间只有**一条**耦合：`adapters/captured.py` 通过 `scanner.ExperimentAdapter` 既有协议接入，`audit`/`rules` 无需知道 lock/run 的存在（Phase 4 Step 2 的 CLI 自动选型**零代码改动**即为证）。
- 对 v0.1 的唯一改动是两处**纯加法**：`cli.py`（docstring + 3 行 import + 3 行注册，共 20+/6−）、`adapters/__init__.py`（import 行 + `captured.install()`，注册在末尾以保持 stable-sort 平票时验收 adapter 优先）。

### 1.2 规模（本轮实测）

| 层 | 文件 | LOC |
|---|---|---|
| v1 采集/验证 | `src/experiment_doctor/v1/**` 15 个 .py（capture 3、lock 3、run 3、verify 3、cli 1、包 2） | 1,658 |
| v1 审计桥 | `src/experiment_doctor/adapters/captured.py` | 378 |
| v1 测试 | `tests/test_v1_{lock_capture,run_capture,verify,audit_integration}.py` | 1,404 |
| v1 端到端驱动 | `scripts/run_v1_full_pipeline_check.py` | 326 |
| v1 fixture | 5 个 `tests/fixtures/v1_*` 目录，共 11 个文件（全部 synthetic 小脚本/配置/CSV） | — |
| 既有 v0.1 | 27 个 .py（含 4 验收 adapter、10 规则） | 不变 |

### 1.3 证据契约（三处不可妥协的不变式，全部有测试）

1. **UNKNOWN 纪律**：lock/run 的每个 leaf 都是 v0.1 `ProvenanceField`，由既有 pydantic 校验器强制「UNKNOWN 不得带 value」「CONFIRMED/SUPPORTED 必须引 source」→ 构造层面无法存入伪造事实。
2. **密码学链**：`canonical_json = json.dumps(body, sort_keys=True, separators=(",",":"), ensure_ascii=False)`；`lock_hash`/`run_hash = "sha256:"+sha256(canonical)`；run 不抄写 lock 字符串而是**重算并双向核对**→ 篡改 lock 当场降级为 UNKNOWN 引用。
3. **两扇门**：进入证据的值只有「直接观测」与「显式声明」两种来源，永不过第三道门（推断）。因此 `--seed` 未声明时，即便 config 里写着 seed，lock 仍是 UNKNOWN；stdout 里写着 `accuracy=99.0` 也不会变成 metric。

## 2. 已实现组件

| 组件 | 入口 | 职责 | 阶段 |
|---|---|---|---|
| Lock schema | `v1/lock/schema.py` | 8 块（identity/code/dataset/configuration/randomness/environment/execution/artifacts）+ seal/body/compute_hash/fields | P1 |
| Capture 层 | `v1/capture/{git,environment,runtime}.py` | subprocess 直读 git（无 GitPython）；`sys.version`/`importlib.metadata`/`platform` 一手观测；cwd/时间戳；`declared_command` | P1 |
| Lock 写入 | `v1/lock/writer.py` | `build_lock`/`write_lock`/`hash_file`/`hash_tree`/`DeclaredInputs`；缺失声明路径记 note 不伪造指纹 | P1 |
| `init` 命令 | `v1/cli.py::init` | `experiment-doctor init [--path][--command --seed --config× --dataset× --output-dir -o]`，回显 lock_hash + 逐字段分级 | P1 |
| Run record | `v1/run/schema.py` | lock_reference / execution / runtime / artifacts / environment + `termination_status`（SUCCESS/FAILED/TIMEOUT/INTERRUPTED/UNKNOWN）+ run_hash | P2 |
| Runner | `v1/run/runner.py` | 核验 lock → 树快照 → `Popen`（stdout/stderr 直写日志）→ `wait(timeout)` → 后快照 diff → 组装 → 写 bundle | P2 |
| `run` 命令 | `v1/cli.py::run` | `experiment-doctor run [--path --lock --run-out --timeout] -- CMD [ARGS…]`，镜像退出码 | P2 |
| Evidence bundle | `experiment-evidence/` | lock + run + stdout.log + stderr.log 四件（顶层恰好这四个；无压缩/上传/签名） | P2 |
| Verify | `v1/verify/{schema,checks}.py` | V001 lock 完整性 / V002 run→lock 链 / V003 run 完整性 / V004 证据齐备 / V005 工件摘要 / V006 路径边界；四态 + `exit_code=1 iff 任一 FAIL` | P3 |
| `verify` 命令 | `v1/cli.py::verify` | 写 `verify.json`/`verify.md`（bundle 内）并回显六项 | P3 |
| captured adapter | `adapters/captured.py` | 把 bundle 翻译成 v0.1 `ExperimentProject`；引用搬家至 bundle 文件以满足 `attached_to_run`；仅 `TIMEOUT→TIME_LIMIT/TRUNCATED_TIME_LIMIT` 一处原因映射 | P4 |
| 端到端驱动 | `scripts/run_v1_full_pipeline_check.py` | 四个树（pre/trad/cap/noseed）跑真实 CLI，产出黄金向量；`--repeat` 全等才退 0 | P5 |

**未实现（明确排除）**：budget 块、metric 提取、tracker 集成（Hydra/MLflow/W&B）、overall/confidence/trust score、压缩上传签名、ED011+ 新规则、任何 stdout/exit-code 推断。

## 3. 验证证据

| 证据 | 内容 | 出处 |
|---|---|---|
| 单测 | v1 共 94 例（21 lock + 22 run + 19 verify + 32 audit-integration），全部在临时目录 copytree fixture + `git init/commit`，不依赖网络或真实项目 | P1–P4 报告 §测试 |
| 端到端黄金 | `tmp/p5/golden.json`：`status_vectors_stable: true`，`repeats: 2`，四树 10 规则向量逐次全等；adapters `{pre: generic, traditional: generic, captured: captured}` | P5 Step 1 |
| capture-first 对照 | 同一棵树 bundle 为唯一变量：ED002 `INCONCLUSIVE→PASS`（声明 seed）、ED003 `INCONCLUSIVE→PASS`（commit 观测）、ED010 `INCONCLUSIVE→PASS`（运行时环境观测）；ED004 保持 INCONCLUSIVE、ED005–ED008 保持 NOT_APPLICABLE/未评估 | P5 §3、golden `cap_before`→`cap` |
| 防火墙（不产生假 PASS） | `noseed` 树：命令里带 `--seed 123`、stdout 里带 `accuracy=99.0`、磁盘上有 `results/metrics.csv`，但 lock `randomness.seed=UNKNOWN` → `ED002 INCONCLUSIVE`（与声明版差一格），`metrics_of_record` 为空 | golden `noseed_firewall` |
| 干净安装 | 临时 venv `pip install .`（非 editable，site-packages 无 `.pth`/egg-link），加载路径解析到 venv 内；wheel 48 条目/42 py、无 pycache/json/log/csv | 本报告 §4.3、Checklist §3 |
| 边界与安全 | 凭据蜜罐不外泄、项目外文件集合逐字节不变、`.git/logs/HEAD` 字节不变、对外部真实仓库审计后 `-newer` 计数 0；v1 import 面无网络/压缩/签名副本 | P5 §6、Checklist §6 |

## 4. 回归状态

### 4.1 本地门禁（本轮 Step 6 重跑）

```
python -X utf8 -m pytest -q      212 passed, 1 skipped in 234.73s
ruff check .                     All checks passed!
ruff format --check .            83 files already formatted
mypy src scripts tests           Success: no issues found in 64 source files
```

- 212 = v0.1 legacy **118 passed + 1 skipped（零漂移）** + v1 94。
- 唯一 skip 为环境性：`tests/test_packaging.py:48`「source-tree run: the distribution is not installed」。
- ⚠ 过程事实（已复原）：Step 4 构建在源树留下 `src/experiment_doctor.egg-info/` 与 `build/`，使该 skip 变 pass，一次跑出 `213 passed`。删除两者后 skip 恢复、ruff/format/mypy 复绿。**未改任何代码**；差异 100% 由构建残留解释。

### 4.2 真实项目回归（沿用 P5 Step 2 记录，本轮**未重跑真实仓库**）

| 套件 | 结果 | 与 Phase 4 基线 |
|---|---|---|
| GMMVI acceptance | 21/21 | sha256 全等 `23fff61805dff0c2…` |
| TorchSSL acceptance | 46/46 | sha256 全等 `a2282b9a44b0c5e1…` |
| CRDA acceptance | 25/25 | sha256 全等 `1f4bedaa1b937312…` |
| Rule acceptance | 19/19 | sha256 全等 `199462cbf6743eff…` |

即：v1 的四层加法对 v0.1 在三条真实项目上的全部结论**零漂移**（连易变字段都不需要豁免，因为这些 JSON 不含时间戳）。

### 4.3 发行物等价性

安装副本（site-packages）跑出的 10 规则向量与源树黄金向量逐项相同：
`ED001 NOT_APPLICABLE / ED002 PASS / ED003 PASS / ED004 INCONCLUSIVE / ED009 INCONCLUSIVE / ED010 PASS`，verify V001–V006 全 PASS，退出码全 0。

## 5. 已知限制

**A. 功能边界（设计如此，不修复）** — 完整 10 条见 `PHASE5_FINAL_VALIDATION_REPORT.md` §8 与 Checklist §7：lock 的 `start_time` 不回填、无 budget 块、无 metric 字段、删除文件只进 note、信号退出码 CLI 层降级、kill 未确认时 UNKNOWN、六类字段刻意不映射、无 tracker 集成、空项目 0 条规则结果、`COVERAGE_FIELDS` 不含 `runtime_environment` 子字段。

**B. 文档状态（RC 缺口，全部为"待人工确认文案"，本轮未改）**

| 文件 | 事实 |
|---|---|
| `README.md` | 只文档化 `scan/audit/rules/adapters` 四命令；缺 `init/run/verify`、缺 capture-first 链路、缺 `captured` adapter；`## Limitations`「Read-only auditor: it never re-runs training」与 `## Output`「Nothing is ever written into the audited project」两句对 v1 的 `run`/`init` 不再全局成立（对 audit 仍成立） |
| `CHANGELOG.md` | 只有 `## v0.1.0`，无 v1.0 条目 |
| `docs/PROJECT_STATE.md` | 仍以 v0.1 为"当前状态"；`:15` 含本地绝对路径（既有已发布内容） |
| `pyproject.toml` / 包 docstring / CLI 组帮助 | 仍写 "Read-only … v0.1"，未提三个新命令 |
| `docs/v1_design/` | 位于**仓库根之外**（`<parent>/docs/v1_design/`，即仓库根的同级目录；`<repo>`/`<parent>` 记法见 `V1_RELEASE_CHECKLIST.md` §0）→ 现有设计/阶段报告**无法被 commit 收录**，也不随包发布 |
| 营销化 | 无问题：README/CHANGELOG/docstring 均不含 AI agent / 自动实验优化 / 模型提升 / 可信度评分 表述，且明文声明无 composite trust score。**无需删改** |

**C. 发布面既有绝对路径（v0.1 遗留，非 v1 引入）**：仓库根 `rule_acceptance.json`（tracked，含 `<parent>/experiment-doctor/...` 形式的本机绝对路径）、`scripts/run_rule_acceptance.py:7-11`、`docs/PROJECT_STATE.md:15`。v1 新增文件 **0 命中**。

## 6. Release blockers

按「阻断强度」排序。**结论：无代码级 blocker**；blockers 全部是发布动作与文案决策。

| # | Blocker | 性质 | 解除方式 |
|---|---|---|---|
| B1 | 未提交：3 M + 12 untracked，远端仍是纯 v0.1.0 | 流程 | 人工批准 §附录 A 的三个 commit（本轮**禁止自动 commit**，未执行） |
| B2 | `docs/v1_design/` 在仓库外 → "docs" commit 落不进去 | 仓库结构 | 决策：移入 `v0.1/docs/v1_design/`，或接受设计文档不入发行物 |
| B3 | 版本号仍 `0.1.0`，且 `1.0.0` 提升需同步改 `__init__.py` 与 `tests/test_packaging.py:RELEASE_VERSION` | 版本策略 | 人工决定 major/minor（纯加法，可选 `0.2.0`）后一次改两处并跑门禁 |
| B4 | README/CHANGELOG/`description`/组帮助对 v1 不完整且 "read-only" 措辞对 `run` 不再全局成立 | 文档准确性 | 按 §7-D4 的建议文案补写；这属发布前必改项（对外陈述与实际能力不符） |
| B5 | 既有 tracked 文件含本地绝对路径与真实项目路径线索 | 隐私/边界 | 人工决定是否清理（清理=改写既有已发布内容，需权衡） |
| — | 代码/测试/安全/回滚 | **非 blocker** | 门禁全绿、真实回归零漂移、凭据与网络扫描干净、回滚点 = HEAD `e17ab18` == `origin/master`（0/0） |

## 7. 需要人工决策的事项

| # | 决策 | 选项 | 备注 |
|---|---|---|---|
| D1 | 是否批准三个 commit | 批准原样 / 调整划分 / 暂缓 | 建议文本见 §附录 A；本轮只生成建议 |
| D2 | 版本策略 | `1.0.0`（把 capture-first 视为里程碑）/ `0.2.0`（强调纯加法） | 两处需同改（B3）；影响 tag 与 PyPI 上传 |
| D3 | 设计文档归属 | 移入库内 / 留在库外 / 摘一段进 README | 决定 B2 与 "docs" commit 能否成立 |
| D4 | README 补写文案 | 由人工定稿 | 建议最小增量：① Quick start 增 `init` / `run -- CMD` / `verify` 三行；② 新增「Capture-first pipeline」小节（lock→bundle→verify→captured adapter，并写明 `run` 会执行用户命令、`init/run` 只在项目根写自身证据文件）；③ Adapters 列表补 `captured`；④ 把两句 "read-only/never writes" 限定为「audit 路径」。**不得**出现 AI agent / 自动优化 / 模型提升 / 可信度评分 |
| D5 | 既有绝对路径是否清理 | 清理 / 保留并说明 / 仅在 .gitignore 层排除未来产物 | 涉及改写已发布内容 |
| D6 | 发布动作本身 | 是否 push / 打 tag / 建 GitHub Release / 上传 PyPI | 任务书本轮明确禁止，未执行任何一项 |
| D7 | v1.1 范围裁决 | tracker 集成（Hydra/MLflow/W&B）、budget 块、结构化 deleted files | 均属新功能，需另立任务书 |

---

## 附录 A：建议的提交划分（**仅为建议，本轮未执行 git commit**）

差异分类（Step 1）：

| 类 | 内容 | 归属 commit |
|---|---|---|
| **A. v1 新功能代码** | `src/experiment_doctor/v1/`（15 个 .py：capture/{git,environment,runtime}、lock/{schema,writer}、run/{schema,runner}、verify/{schema,checks}、cli.py、4 个 `__init__.py`）、`src/experiment_doctor/adapters/captured.py`、`adapters/__init__.py`(M)、`cli.py`(M) | commit 1 |
| **B. 测试** | `tests/test_v1_{lock_capture,run_capture,verify,audit_integration}.py`、`tests/fixtures/v1_{basic,run,verify,audit,full}_project/`、`tests/test_packaging.py`(M，adapter 注册集合)、`scripts/run_v1_full_pipeline_check.py`（端到端驱动，属验证资产而非发行载荷） | commit 2 |
| **C. 文档** | `docs/v1_design/`（设计 2 份 + 阶段报告 5 份 + `V1_RELEASE_CHECKLIST.md` + 本报告）—— **当前在仓库外，需 D3 决策后才能落入 commit**；以及待补的 `README.md`/`CHANGELOG.md`（B4/D4） | commit 3 |
| **D. 临时验证产物（不提交）** | `tmp/`（307 文件、38 MB，含 `tmp/p5/golden.json`、四份 acceptance JSON、本轮 `tmp/rc_venv`、`tmp/rc_demo`、`tmp/rc_out`）——已被 `.gitignore:20 tmp/` 排除；`src/experiment_doctor.egg-info/`、`build/` 已在 §4.1 说明中删除 | 不提交 |

建议 commit message（三行，任务书给定的语义）：

```
commit 1: feat: add experiment capture and verification pipeline
          init/run/verify 三命令 + lock/run schema + capture 层 + verify V001–V006
          + captured adapter。对 v0.1 为纯加法：rules/schema/audit/scanner/provenance
          与四个验收 adapter 逐字节未动。

commit 2: test: add v1 end-to-end validation
          94 个 v1 单测（21+22+19+32）+ 5 个 synthetic fixture
          + scripts/run_v1_full_pipeline_check.py 黄金驱动；test_packaging 的
          adapter 集合随 captured 注册更新。

commit 3: docs: finalize v1 MVP documentation
          五份阶段报告 + 设计/实施计划 + RC 清单与终报；README/CHANGELOG 的
          v1 补写（依赖 D3 仓库归属与 D4 文案定稿，否则此 commit 无法成立）。
```

---

*RC 整理终点。工作树状态与本报告开头一致：3 M + 12 untracked，HEAD `e17ab18` 未移动；未 commit、未 push、未 tag、未上传 PyPI、未进入 v1.1。*
