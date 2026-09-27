# Experiment Doctor v1.0.0 — 交接报告（V1_HANDOFF_REPORT）

- 日期：2026-09-27
- 阶段：Post-Release Freeze & Handoff（Step 5 产物）。本轮**只记录**：不改 schema、不改 rules、不新增 adapter、不改 CLI 行为、不修非阻塞 limitation、不重设计架构、不做第三方项目扩展验证
- 读者：下一位接手 v1.0.0（或其后续版本）的人。假设他从未看过本项目历史对话
- 三份配套记录：发布过程 `V1_RELEASE_REPORT.md`；冻结快照与安全终审计 `FINAL_RELEASE_STATE.md`；能力边界 `V1_FINAL_STATUS.md`；本报告是入口
- 一句话定位：**Experiment Doctor 是一个只读的 ML 实验溯源审计工具。它证明一份实验记录说了什么、凭什么说、以及哪里它没敢说。它不判断实验好坏。**

---

## §1 Release identity

| 项 | 值 | 核对方式 |
|---|---|---|
| 包名 / 版本 | `experiment-doctor` / **`1.0.0`** | `pyproject.toml` + `src/experiment_doctor/__init__.py:__version__` |
| release commit | `fb3a24200a56724816906018a60c4a54b6149ab1` | `git rev-parse v1.0.0^{}` |
| tag | `v1.0.0`（annotated），tag object `6e85a56a6609c52f7661fea57b84188c3469df41` | `git rev-parse v1.0.0` |
| 分支 | `master`（本地与远端同名；仓库从未有 `main`） | `git branch -a` |
| 冻结时 HEAD | `09a35cb2cd6b6f181599aae88a4eeda76d618188` | release commit 之后仅两笔 docs |
| 远端 | `https://github.com/xihaian251/experiment-doctor.git`，`git rev-list --left-right --count origin/master...HEAD` = `0 0` | 只读核查 |
| GitHub Release | https://github.com/xihaian251/experiment-doctor/releases/tag/v1.0.0（public，非 draft，非 prerelease） | API + HTTP 200 |
| PyPI | https://pypi.org/project/experiment-doctor/1.0.0/ （`/simple/` latest = 1.0.0；releases = `0.1.0`, `1.0.0`） | JSON API |
| 发布通道 | GitHub Actions `publish-pypi.yml` run `36322803984`（`completed/success`），**Trusted Publishing**（`environment: pypi` + `id-token: write`）。无 API token、无 `.pypirc`、无 twine | workflow 记录 |
| wheel | 132,523 B · `2bf8aa04a3b1ee8f065ea9d4c0a79cd13c958b75a7bdd36941e7bcb6705a56b2` | PyPI digest == GitHub 资产 digest == 本机 `dist/`，三方逐字符一致 |
| sdist | 144,788 B · `6c4606aeb278949ca59f3ea9b0b2aeee88ad7039eda991b8d5d436fec83eda24` | 同上 |

**版本单一来源**：`pyproject.toml` 用 `dynamic = ["version"]` + `attr = "experiment_doctor.__version__"`；第二把锁在 `tests/test_packaging.py:RELEASE_VERSION`。改版本必须同时改这两处，否则测试红。发行元数据文案（作者、摘要、classifiers）在 RC 阶段人工决定为「不动」，v1.0.0 沿用 v0.1 文案，这是**有意**的，不是遗漏。

## §2 Architecture frozen state

发布后冻结面：**自 v0.1.0 发布线 `e17ab18` 起，`schema.py` / `rules/` / `audit.py` / `scanner.py` / `provenance.py` / 四个验收 adapter 全部 0 改动**（`git diff --name-only e17ab18..HEAD -- <上述路径>` 为空）。v1 的全部改动是**加法**。

```
src/experiment_doctor/
├── schema.py audit.py scanner.py report.py provenance.py cli.py   # v0.1 冻结核心
├── rules/                    # ED001–ED010，10 个文件 + base/__init__（冻结）
├── adapters/                 # gmmvi / torchssl / crda / generic（冻结）
│   └── captured.py           # v1 新增：把 evidence bundle 映射进 v0.1 溯源模型
└── v1/                       # v1 新增，共 15 个 .py
    ├── cli.py                # init / run / verify 三个命令
    ├── lock/  schema.py writer.py        # experiment.lock.json，8 块 + lock_hash
    ├── run/   schema.py runner.py         # experiment.run.json，run_hash + lock_reference
    ├── verify/ schema.py checks.py        # V001–V006 + verify.json/md
    └── capture/ environment.py git.py runtime.py   # 直接观察层
```

冻结的行为不变量（改任何一条都算 breaking change，必须另开版本决策）：

1. **两道门**：值只能来自「直接观察」或「显式声明」。二者皆无 ⇒ `UNKNOWN`。`init` 不给 `--command` 时 `execution.command=UNKNOWN`，`run` 真跑了才记 `CONFIRMED`；无 git 仓库 ⇒ `code.*=UNKNOWN` 且 `ED003 INCONCLUSIVE`，**绝不填一个 PASS 冒充**。
2. **不推断结果**：不由 exit code 推断训练成功，不解析 stdout 猜 metric，不做 metric extraction，不产 `overall_score` / `confidence` / `trust_score`。`rule_summary` 只有 counts + 一句「no overall verdict」的 note。
3. **封条可自证**：canonical JSON = `sort_keys=True, separators=(",",":"), ensure_ascii=False`；`lock_hash` / `run_hash` = `sha256:` + 摘要，verify 时**重算**再比对，从不复制存储值。`schema_version="1.0"` 固定在 lock/run/verify 三处。
4. **四态**：`PASS / FAIL / INCONCLUSIVE / NOT_APPLICABLE`（verify 另有 `NOT_RUN` 计数位）。`verify` 退出码 1 当且仅当存在 FAIL。
5. **审计侧只读**：`audit` 从不写、修、重序列化 lock/run 文件。

## §3 Validation evidence

| 层次 | 证据 | 位置 |
|---|---|---|
| 代码测试 | `212 passed, 1 skipped`（237.01s，`-rs` 确认 skip 原因仍为环境性） | 冻结轮复跑（HEAD `09a35cb` + 本轮文档），与发布前基线逐项相同 |
| 静态门禁 | `ruff check` All checks passed；`ruff format --check` **100 files already formatted**（计数含 Markdown）；`mypy src scripts tests` Success in 64 files | 同上 |
| 真实项目回归（四套向量，未重跑，沿用基线） | GMMVI **21/21** `23fff61805dff0c2`；TorchSSL **46/46** `a2282b9a44b0c5e1`；CRDA **25/25** `1f4bedaa1b937312`；Rule acceptance **19/19** `199462cbf6743eff` — 四套 total_diffs=0，输出 JSON sha256 与历史相同 | `PHASE5_FINAL_VALIDATION_REPORT.md:138-144` |
| 端到端 golden | `v1_full_project` 全链路双次一致（init→run→verify→audit），V001–V006 全 PASS，captured adapter 规则向量与 Phase 5 黄金一致 | `PHASE5_FINAL_VALIDATION_REPORT.md` |
| 干净安装 | 非 editable 安装 wheel 后跑通同一链路；`pip install --no-cache-dir experiment-doctor==1.0.0` 于发布后 fresh venv 成功，`pip check` 无破损依赖 | `V1_RELEASE_REPORT.md` §5.1、§6 |
| 冻结轮复现 | 本轮在源码树重跑 init→run→verify→audit 合成链路：`verify exit=0`（V001–V004+V006 PASS、V005 NOT_APPLICABLE）、`audit exit=0`（`adapter=captured`，6 条规则 evaluated：ED002/003/010 PASS，ED004/009 INCONCLUSIVE，ED001 NOT_APPLICABLE，ED005–ED008 NOT_RUN） | 本报告 §7，命令与输出逐字记录 |
| 安全终审计（Step 4） | 158 个仓库文件（152 tracked + 冻结新增 6）+ wheel 48 条目 + sdist 66 条目 + `git config` 26 行 + 提交对象：**0 凭据 / 0 token / 0 Bearer / 0 私钥 / 0 本机用户名 / 0 邮箱（tracked 文件）**；发行物 **0** 真实本机绝对路径（sdist 仅 1 处合成串 `C:/Windows/stderr.log`）；仓库文档层 12 处路径命中已逐类定性（5 处真实历史证据保留、2 处是报告自述扫描模式、2 处合成、1 处 `wandb:` 同形误报、2 处本轮文档引用）；1 项新增 **P3** 非阻断暴露（提交作者邮箱随 commit 对象公开，本文档掩码书写） | `FINAL_RELEASE_STATE.md` §5（含扫描器口径与两条踩坑教训） |

结论：**P0 = 0，release-blocking P1 = 0**；冻结轮未新增任何阻断项。

## §4 Public interfaces（v1.0.0 起视为稳定面）

**CLI：7 个命令**（`python -m experiment_doctor` 或安装后 `experiment-doctor`）。注意 v1.0.0 的 help 首行仍写「v0.1」，属文案遗留（§5 A5），语义上 scan/audit/rules/adapters 是 v0.1 面、init/run/verify 是 v1 面。

| 命令 | 关键参数 | 产物 |
|---|---|---|
| `scan <PATH>` | — | 家族/候选/覆盖度打印 |
| `audit <PATH>` | **PATH 为必填参数**（与 init/verify 不同） | `experiment-doctor-report/report.json` + `report.md` |
| `rules` / `adapters` | — | 10 条规则与 5 个 adapter 的自述 |
| `init [PATH]`（默认 `.`） | `--command --seed --config(可重复) --dataset(可重复) --output-dir -o` | `experiment.lock.json` |
| `run [--path --lock --run-out --timeout] -- <cmd...>` | 命令必须放在 `--` 之后 | `experiment.run.json` + `experiment-evidence/` |
| `verify [PATH]`（默认 `.`，可给 bundle 或 project 目录） | — | `experiment-evidence/verify.json` + `verify.md` |

**`experiment.lock.json`**（`schema_version` + 8 块 + `lock_hash`，顺序即 canonical 顺序）：
`schema_version` · `identity{experiment_id, created_at}` · `code{repository, commit, dirty, diff_hash}` · `dataset{paths, fingerprints}` · `configuration{config_files, config_hash}` · `randomness{seed, seed_source}` · `environment{python_version, packages, platform}` · `execution{command, cwd, start_time}` · `artifacts{output_directory}` · `lock_hash`

**`experiment.run.json`**：
`schema_version` · `lock_reference{lock_hash, lock_path}` · `execution{command, cwd, pid, start_time, end_time, exit_code}` · `runtime{stdout_path, stderr_path, timeout_status, timeout_seconds}` · `artifacts{created_files, modified_files, note}` · `environment{python_version, packages, platform}` · `termination_status` · `run_hash`

**每个可溯源字段统一形状**：`{value, status, source, confidence_note}`，`status ∈ {CONFIRMED, DECLARED, UNKNOWN, ...}`；`source` 为 `SourceRef{path, key, line, artifact_id, note}`。这个四元组是「凭什么这么说」的载体，字段增减属 breaking change。

**evidence bundle**：目录 `experiment-evidence/`，必需四件 `experiment.lock.json` `experiment.run.json` `stdout.log` `stderr.log`（`REQUIRED_BUNDLE_FILES`），外加 verify 写出的 `verify.json/md`。

**verify 报告**：`{schema_version, bundle_identity{bundle_path, lock_hash_expected, lock_hash_observed, run_hash_expected, run_hash_observed}, checks[{check_id, status, evidence, message}]}`。六检语义（本轮实测确认，注意 V002/V003 与直觉相反）：

| 检查 | 语义 |
|---|---|
| V001 | lock 正文重算 == 自身 `lock_hash`（改过封条即 FAIL） |
| V002 | **run → lock 链条完整**（run 声明的 `lock_reference.lock_hash` vs lock 实测重算） |
| V003 | **run 正文重算 == 自身 `run_hash`** |
| V004 | 必需四件齐备且非空 |
| V005 | run 声明的 `created_files/modified_files` 摘要在盘上复核；无声明 ⇒ `NOT_APPLICABLE`（不是错误） |
| V006 | 路径声明不越出 bundle/project 边界（`execution.cwd` 定义边界故豁免，自由文本 note 豁免） |

**audit `report.json` 顶层键（顺序固定）**：`scan` · `audit` · `rules` · `rule_summary` · `project`。规则条目字段：`rule_id, status, severity, summary, measurements, limitations, recommendation`。`rule_summary = {counts, note}`，**无综合分**。

## §5 Known limitations（只记录，本轮不修）

| 编号 | 事实 | 为什么不算缺陷 |
|---|---|---|
| A1 | **无 tracker 集成**：不认识 MLflow/W&B/SwanLab 服务端，只能审计盘上 artifact 与自产 bundle | v1 边界即「capture-first + 只读」，接入 tracker 属 v1.1 议题 |
| A2 | **无 MLflow / Hydra 读取器**：`--config` 只接受文件路径并指纹化，不解析 Hydra 组合配置语义 | 解析框架配置需要「推断」，与两道门纪律冲突 |
| A3 | **无 metric extraction**：不读 stdout 猜指标，不做曲线/最优值提取 | 明令禁止；指标只能作为被审计项目里的既有声明出现 |
| A4 | **删除检测有界**：`run` 只记 `created_files/modified_files` 摘要，被删文件仅体现在 `artifacts.note`，无独立「缺失即 FAIL」判定 | V005 只能复核「有声明」的项 |
| A5 | **CLI 文案遗留 v0.1**：`--help` 首行与 `scan/audit/rules/adapters` 描述仍写 v0.1 | 改它 = 改 CLI 行为面，冻结轮禁止 |
| A6 | **证据与报告会内嵌本机绝对路径**（`execution.cwd`、`bundle_path`、report 里的 project 路径）。本轮实测：合成的 lock/run/verify/audit 四件产物各含 1 条 `F:\MLResearch\...` | 绝对路径是 V006 边界判定的依据，去掉就失去越界检测能力。附带后果：把 bundle/report 直接对外发布前需自行决定是否脱路径 |
| A7 | **sdist 不可字节复现**：固定 `SOURCE_DATE_EPOCH` 下 wheel 可逐字节一致，sdist 不行（成员顺序/时间戳由 setuptools 决定） | 因此发布流程以「CI 产物为准 + 三方哈希核对」，不靠本地重建 |
| A8 | **`publish-pypi.yml` 里版本号是字面量**（step 名 + 两个 `ls` + 一个 assert 共 4 处）。v1.0.0 就是靠人工改成 1.0.0 才发布的（`fb3a242`） | 下次发布**必须**先改这 4 处，否则 workflow 在上传前失败 |
| A9 | **提交作者邮箱随 commit 对象公开**（GitHub commits API 实测返回） | 修复需 rewrite history + 强推 + 重签 tag，与「tag 已公开、不改历史」冲突；须另开轮并明确授权 |
| A10 | **PyPI 索引有传播延迟**：发布后 `pip install ==1.0.0` 首次失败（`from versions: 0.1.0`），轮询 `/simple/` 约 2 分钟后成功 | 已作为事实记录在发布报告，非缺陷 |
| A11 | 仓库内 **5 个文件带真实本机绝对路径**：`EXPERIMENT_DOCTOR_V0_1_MVP_REPORT.md:3-4`、`EXPERIMENT_DOCTOR_V0_1_RULESET_REPORT.md:11`、`docs/PROJECT_STATE.md:15`（`F:\MLResearch\...`）+ `rule_acceptance.json`、`scripts/run_rule_acceptance.py:7-11`（`F:/MLResearch/...`）。另有 2 处是历史报告**在句子里引用扫描模式串**（RC2 `:88,100`、FINAL `:129`），2 处是合成串（`PHASE3_VERIFY_REPORT.md`、`tests/test_v1_verify.py`） | 前 5 处属已发布历史事实证据，任务书明令不得改写；其余不是泄露 |
| A12 | **`test_packaging.py:48` 会因构建残留而假 pass**：源树里若留 `build/` 或 `src/experiment_doctor.egg-info/`，该 skip 静默变 pass，出现假象 `213 passed` | 规程：每次构建后删净，并用 `-rs` 复核 skip 仍在 |
| A13 | **安全扫描不得用 `grep`**：以反斜杠收尾的模式（`grep 'C:\\'`）会报 `grep: Trailing backslash` 并**静默返回空**，等于假通过；drive-letter 正则还会把 `wandb:` 里的 `b:` 吃成路径（`scripts/make_mini_fixture.py:144` 即本轮实测误报） | 规程：用 Python 字节级正则 + 允许 1/2 个分隔符 + 排除 `scheme://` + 人工复核每条命中 |
| A14 | **文档哈希随 EOL 变**：本机 `core.autocrlf=true`，`docs/v1/` 里 3 份早期报告（`V1_RELEASE_REPORT.md`、`V1_RELEASE_CANDIDATE_REPORT.md`、`V1_RELEASE_CHECKLIST.md`）工作树是 CRLF 而 git blob 是 LF，两者 sha256 **不同**（例：`96bded16…` vs `cfc7b266…`）。本轮新增文档工作树与 blob 一致，但换台 Windows 机器检出后同样会漂移 | 规程：文档一律以 **git blob** 为哈希口径（`git cat-file blob HEAD:<path> \| sha256sum`），发行物是二进制不受影响。`release/v1.0.0/VALIDATION_REPORTS_INDEX.md` §2/§4 已按该口径记录并给出命令 |

## §6 Future development boundary

本报告之后，v1.0.0 视为**已冻结**。任何下列动作都必须**另开一轮 planning 任务书**，不得在「顺手」的维护轮里做：

- 新规则（ED011+）、ED001–ED010 的语义/严重度变更、冻结 schema 字段含义变更、CLI 参数面变更 → 属版本决策（先答「是不是 breaking」再答「几号版本」）。
- tracker / MLflow / Hydra / 任意框架 reader、metric 自动提取、成功与否自动推断 → 直接触碰 §2 不变量 1/2/3，不是「加个功能」，需要重新设计证据等级。
- 综合评分 / 可信度排名 / agent 化自动改进 → 项目的**产品立场**就是不做，重启需先推翻该立场。
- 第五个验收项目、GUI、自动优化 → 已明确排除，v1 MVP 不以覆盖面为目标。
- 触及 §5 的 A1–A4、A7、A11 → 需要显式授权；A8/A10/A12 是**操作规程**，按字面执行即可，不必「优化掉」。
- 措辞纪律（沿用全期）：禁止 AI agent / automatic improvement / 模型提升 / 可信度评分 这类宣传语；禁止「压缩/上传/签名」类副作用步骤；UNKNOWN 不是错误。

## §7 Reproducibility instructions

以下命令**本轮逐条实跑通过**（Windows git-bash，Python 3.13，HEAD `09a35cb`）。两个坑先说：`PYTHONPATH` 必须给**绝对路径**（相对 `src` 在 `cd` 进项目目录后立即失效）；`PYTHONIOENCODING=utf-8` 不加会在中文 Windows 上因 GBK 编码崩打印。

```bash
# 0) 取源码（tag 已公开）
git clone https://github.com/xihaian251/experiment-doctor.git && cd experiment-doctor
git checkout v1.0.0                     # 应解引用到 fb3a24200a56724816906018a60c4a54b6149ab1

# 1a) 源码树跑（不安装）
export PYTHONIOENCODING=utf-8
export PYTHONPATH=$PWD/src              # 必须是绝对路径
python -X utf8 -m experiment_doctor --help     # 7 个命令：scan audit rules adapters init run verify

# 1b) 或装公开发行物（哈希见 §1）
python -m venv .venv && .venv/Scripts/activate    # Linux: source .venv/bin/activate
pip install --no-cache-dir experiment-doctor==1.0.0
pip check && python -c "import experiment_doctor as e; print(e.__version__); print(e.__file__)"
#   期望 1.0.0 + site-packages 路径（证明不是源码树）

# 2) 最小合成链路（本轮实测）
mkdir -p repro/proj && cd repro/proj
printf 'print("hello")\n' > train.py
python -X utf8 -m experiment_doctor init --seed 42 --config train.py
#   lock written: experiment.lock.json / lock_hash: sha256:...
#   execution.command=UNKNOWN  ← 没给 --command，必须是 UNKNOWN（两道门的验收点）
python -X utf8 -m experiment_doctor run -- python train.py
#   termination: SUCCESS，execution.command=CONFIRMED，lock_reference 指向上一行 lock_hash
python -X utf8 -m experiment_doctor verify          # exit 0
#   V001 PASS / V002 PASS / V003 PASS / V004 PASS / V005 NOT_APPLICABLE / V006 PASS
python -X utf8 -m experiment_doctor audit .         # 注意：audit 的 PATH 必填
#   adapter=captured ... rule_fail=0 rule_inconclusive=2
#   写出 experiment-doctor-report/report.json + report.md
```

门禁复跑（仓库根目录）：

```bash
export PYTHONIOENCODING=utf-8 PYTHONPATH=$PWD/src
python -X utf8 -m pytest -q              # 期望 212 passed, 1 skipped（出现 213 说明有构建残留 → §5 A12）
python -X utf8 -m pytest -q -rs          # 确认 skip 原因仍是 "source-tree run: the distribution is not installed"
python -X utf8 -m ruff check .
python -X utf8 -m ruff format --check .  # 95 files already formatted
python -X utf8 -m mypy src scripts tests # Success: no issues found in 64 source files
```

重建发行物（仅供比对，**不要**当作发布源，见 §5 A7）：

```bash
pip install build
SOURCE_DATE_EPOCH=0 python -m build      # wheel 可逐字节复现；sdist 与 PyPI 那份哈希不同属预期
rm -rf build/ src/experiment_doctor.egg-info/   # 必须删净，否则 §5 A12 假 pass
sha256sum dist/*                          # 与 §1 的公开哈希比对
```

**冻结产物目录**：`release/v1.0.0/`（哈希清单 `SHA256SUMS.txt`、发布报告冻结副本、报告索引 `VALIDATION_REPORTS_INDEX.md`）。该目录刻意**不含源码、不含用户数据、不含环境变量**。

该目录不会污染后续发行物：本轮把包构建到临时目录做过实测——wheel 仍为 48 条目、sdist 顶层仍只有 `LICENSE PKG-INFO README.md pyproject.toml setup.cfg src/ tests/`，`release/`、`docs/`、`scripts/` 均**不在**载荷中（因为没有 `MANIFEST.in`，setuptools 只收 `src/` + `tests/` + 顶层少量文件）。注意本地构建的 sdist 成员数（78）与 PyPI 那份（66）不同，属 §5 A7 的不可复现范围，比对的是**拓扑**而非字节。

---

*接手第一读序：本报告 §1→§4（身份/结构/接口）→ `FINAL_RELEASE_STATE.md` §5（安全终审计）→ `V1_FINAL_STATUS.md`（保证与不做的清单）→ 需要历史时看 `V1_RELEASE_REPORT.md` 与 `V1_RELEASE_FINAL_REPORT.md`。*
