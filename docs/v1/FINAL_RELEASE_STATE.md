# Experiment Doctor v1.0.0 — FINAL RELEASE STATE（Post-Release Freeze 快照）

- 日期：2026-09-27
- 阶段：Post-Release Freeze & Handoff。只读核查 + 记录，不改 schema / rules / adapter / CLI 行为，不修非阻塞 limitation，不进入 v1.1
- 落点说明：任务书只给文件名，本文件按 v1 文档集惯例放在 `docs/v1/`（与 `V1_RELEASE_REPORT.md` 同目录，便于互相引用）
- 核查人：发布执行会话（同一会话延续），全部命令为只读

---

## 1. 发布身份

| 项 | 值 |
|---|---|
| 版本 | **`1.0.0`** |
| release commit | `fb3a24200a56724816906018a60c4a54b6149ab1` |
| tag | `v1.0.0`，annotated；tag object `6e85a56a6609c52f7661fea57b84188c3469df41` |
| `git rev-parse v1.0.0^{}` | `fb3a242…` == release commit ✓ |
| 分支 | `master`（本地与远端同名；本仓库从无 `main`） |
| 核查时 HEAD | `09a35cb2cd6b6f181599aae88a4eeda76d618188`（= release commit 之后仅两笔 docs：发布报告 + 其勘误） |
| 本地 vs 远端 | `git rev-list --left-right --count origin/master...HEAD` = **`0 0`**（完全同步）；`git ls-remote` 的 `refs/heads/master` = `09a35cb…`、`refs/tags/v1.0.0^{}` = `fb3a242…` |
| origin | `https://github.com/xihaian251/experiment-doctor.git` |
| GitHub Release | https://github.com/xihaian251/experiment-doctor/releases/tag/v1.0.0 （public / 非 draft / 非 prerelease，HTTP 200 实测） |
| PyPI | https://pypi.org/project/experiment-doctor/1.0.0/ ；`info.version`（latest）= **1.0.0**；releases = `['0.1.0', '1.0.0']` |
| 发布方式 | GitHub Actions `publish-pypi.yml` run `36322803984`（`completed / success`）经 **Trusted Publishing**；无 API token、无 `.pypirc`、无 twine |

## 2. 发行物哈希（公开物 = 本地留存 = 已核对一致）

| 文件 | 字节 | sha256 |
|---|---|---|
| `experiment_doctor-1.0.0-py3-none-any.whl` | 132,523 | `2bf8aa04a3b1ee8f065ea9d4c0a79cd13c958b75a7bdd36941e7bcb6705a56b2` |
| `experiment_doctor-1.0.0.tar.gz` | 144,788 | `6c4606aeb278949ca59f3ea9b0b2aeee88ad7039eda991b8d5d436fec83eda24` |

- 三个来源同一对哈希：PyPI 登记的 `digests.sha256`、GitHub Release 资产的服务端 `digest`、本机 `dist/` 下文件的 `sha256sum` **逐字符相同**（资产在发布核对后经人工授权替换为 PyPI 那一份，见 `V1_RELEASE_REPORT.md` §8 Q2）。
- 本机 `dist/` 由 CI（Linux / setuptools 84.0.0）产物的下载件构成；本地 Windows 构建的同版本另一对哈希（`686226b2…` / `76265fb7…`）**不是**公开物，差异已证明为行尾 + `WHEEL` 生成器字样（`V1_RELEASE_REPORT.md` §5.1）。

## 3. 工作区状态

| 检查 | 结果 |
|---|---|
| `git status --porcelain` | **空**（clean）✓ |
| 未跟踪的发布产物 | 无。`dist/`、`.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`、`__pycache__/` 全部被 `.gitignore` 覆盖，属 **ignored 而非 untracked**（`git status --porcelain --ignored` 逐条确认）；发布用一次性脚手架（临时 venv、smoke 目录、GitHub API 响应件）已在发布阶段结束时删除 |
| 源码树新增文件 | 本文件与 `release/v1.0.0/`、`docs/v1/V1_FINAL_STATUS.md`、`docs/v1/V1_HANDOFF_REPORT.md` 四组，全为文档/记录，无 `.py` |

## 4. 冻结时的门禁复跑（HEAD `09a35cb` + 本冻结轮的文档，工作树含全部 Step 产物）

| 门禁 | 结果 |
|---|---|
| `python -X utf8 -m pytest -q -rs` | **212 passed, 1 skipped**（237.01s） |
| `ruff check .` | All checks passed!（rc=0） |
| `ruff format --check .` | **100 files already formatted**（计数含 Markdown；文档增加会抬高该数，非测试面变化） |
| `mypy src scripts tests` | Success: no issues found in 64 source files |
| skip 项 | `tests/test_packaging.py:48`「source-tree run: the distribution is not installed」— 环境性跳过（若 `build/` 或 `src/experiment_doctor.egg-info/` 残留会变假 pass，故本轮核查两者均不存在；`-rs` 已实测确认 skip 仍在） |
| 门禁后 `git status --porcelain` | 仅本冻结轮的 4 组新文档，无源码改动 ✓ |

与发布前基线（`V1_RELEASE_FINAL_REPORT.md` §5.1）**逐项相同**：文档提交未触碰任何测试计数。

## 5. 安全终审计（Step 4，只登记不修改）

扫描器：`tmp/security_final_audit.py`（本轮临时件，`tmp/` 已被 gitignore，不入库）。范围与口径：

- **158 个仓库文件** = 152 tracked ∪ 本次冻结新增 6 个（`docs/v1/` 3 份 + `release/v1.0.0/` 3 份）
- **wheel 48 条目** + **sdist 66 成员**（`dist/` 下即公开下载件，哈希见 §2）
- `git config --list --show-origin` 26 行 + 提交对象作者字段

> 扫描器口径教训（两条，都是本轮真实踩到后修正的）：
> 1. `grep 'C:\\'` 之类以反斜杠结尾的模式会报 `grep: Trailing backslash` 并**静默给出空结果**；一律改用 Python 字节级正则。
> 2. -drive 路径正则须允许 1 个或 2 个分隔符（Markdown 里写 `F:\MLResearch`，JSON 里写 `F:\\MLResearch`），且必须排除 `scheme://` 与**同形误报**：`scripts/make_mini_fixture.py:144` 的 YAML 字面量 `wandb:` 里的 `b:` 会被drive-letter 正则吃掉，人工核对后判为误报。首版扫描因正则要求「恰好 2 个分隔符」而漏计单反斜杠写法，本节数字为**改正后重跑**结果。

### 5.1 凭据类：0 命中

| 模式 | 158 仓库文件 | wheel 48 | sdist 66 | git config |
|---|---|---|---|---|
| `ghp_*` / `github_pat_*` / PyPI token 前缀 / `AKIA*` / `xox*-` / 私钥 PEM 头 | 0 | 0 | 0 | 0 |
| `Bearer <16+ 字符>` | 0 | 0 | 0 | — |
| `api_key/secret/password/access_token = <12+ 字符值>` | 0 | 0 | 0 | 0 |
| `user:pass@host` 形式的远端 URL | 0 | 0 | 0 | 0 |
| 邮箱地址 | 仅本审计文档自身（见 §5.3，已按 `3796…@qq.com` 掩码书写）；152 tracked 文件 **0** | 0 | 0 | 1 行（本机全局配置，见下） |

- 早前两版扫描出现的 `pypi-` 字面命中经上下文核对为**误报**：`pypa/gh-action-pypi-publish@release/v1` 动作名（`.github/workflows/publish-pypi.yml`、`docs/RELEASE_CHECKLIST.md`）。
- 发布全程未落盘 token：凭据只存在于 shell 变量，用后 `unset`，未写文件、未嵌入 remote URL。`git config` 26 行中唯一敏感项是全局 `user.email`（本机配置文件，不属于仓库内容）。

### 5.2 绝对路径：发行物 0 真实本机路径 / 仓库 12 文件命中（逐类定性）

| 类别 | 文件 | 形态 | 定性 |
|---|---|---|---|
| **wheel（48 条目）** | — | **0 命中** | 干净（唯一 `:` 形态命中是 LICENSE 的 Apache URL） |
| **sdist（66 成员）** | `tests/test_v1_verify.py` | `C:/Windows/stderr.log` | 测试合成字面量，**非**本机路径；真实本机路径 **0** |
| 真实本机路径 · 报告类 | `EXPERIMENT_DOCTOR_V0_1_MVP_REPORT.md:3-4`、`EXPERIMENT_DOCTOR_V0_1_RULESET_REPORT.md:11`、`docs/PROJECT_STATE.md:15` | `F:\MLResearch\...` | v0.1 已发布历史事实证据，任务书明令**不得改写** → 只登记 |
| 真实本机路径 · 脚本/数据 | `rule_acceptance.json`（`F:/MLResearch` + JSON 转义 `F:\\MLResearch`）、`scripts/run_rule_acceptance.py:7-11`（`F:/MLResearch` ×4 上游目录） | 同上 | 19/19 规则验收的可复现入口，属历史证据链 → 只登记 |
| 报告里引用的「扫描模式串」 | `docs/v1/V1_RELEASE_CANDIDATE_RC2_REPORT.md:88,100`（`C:\Users` 作为扫描模式 + `F:/MLResearch`）、`docs/v1/V1_RELEASE_FINAL_REPORT.md:129`（`C:\<用户目录>`） | 反斜杠 | 这些句子本身在**描述扫描规则**，非泄露；保留 |
| 合成示例路径 | `docs/v1/PHASE3_VERIFY_REPORT.md`（`C:/Windows/...`）、`tests/test_v1_verify.py` | 正斜杠 | 与 sdist 同源，测试/文档用合成串 |
| 同形误报 | `scripts/make_mini_fixture.py:144` | `wandb:` 中的 `b:` | **误报**，非路径 |
| 本轮新增文档自指 | `docs/v1/FINAL_RELEASE_STATE.md`、`docs/v1/V1_HANDOFF_REPORT.md` | 反斜杠 | 本节与交接报告**引用**了上述路径形态；已在 §5.3 说明掩码处理 |
| `/home/...`、`/Users/<名>` | 除本审计文档自指的模式引用外 | — | 152 tracked 文件 **0 命中** |
| 本机 Windows 用户名（UTF-8 字节） | — | **0**（仓库 / wheel / sdist 全零） | — |

### 5.3 个人标识：3 类，分类后均**不静默改**

| 标识 | 出现位置 | 定性 |
|---|---|---|
| GitHub 账号 `xihaian251` | 7 个文件：`docs/PROJECT_STATE.md`、`docs/v1/EXPERIMENT_DOCTOR_V1_IMPLEMENTATION_PLAN.md`、`docs/v1/V1_RELEASE_CHECKLIST.md`、`docs/v1/V1_RELEASE_REPORT.md`、`release/v1.0.0/V1_RELEASE_REPORT.md`，以及本轮新增的 `docs/v1/FINAL_RELEASE_STATE.md`、`docs/v1/V1_HANDOFF_REPORT.md` | **公开仓库地址本身的一部分**，无法也不应去除 |
| PyPI 作者笔名 `beihai` | `pyproject.toml`（随包进入 wheel `METADATA`、sdist `PKG-INFO` / `pyproject.toml` / `src/experiment_doctor.egg-info/PKG-INFO`）、`docs/v1/V1_RELEASE_CHECKLIST.md`、本轮审计文档 | RC 阶段**人工决定保留**的发布元数据；非姓名非邮箱 |
| 提交作者邮箱（形如 `3796…@qq.com`，本文件刻意不完整复制） | **不在** wheel/sdist 任何条目；**在** git 提交对象，因而已随 push 公开 | **P3 非阻断隐私暴露**。本轮实测 GitHub commits API（`?per_page=3`）对 `fb3a242`/`c0ddc63`/`09a35cb` 三笔均返回该邮箱。修复需 rewrite history + 强推 + 重签已公开的 tag，与「不改历史、不静默编辑」边界冲突 → **只登记，不处置**；若要处理须另开一轮并显式授权 |

补充：本审计文档对邮箱采用**掩码书写**，避免把已公开的地址在仓库 blob 里二次扩散；历史报告中的任何事实证据**未做改写**。

### 5.4 结论

release artifact（wheel + sdist）与 package metadata 层面：**0 凭据、0 真实本机绝对路径、0 本机用户名、0 邮箱**，个人标识仅剩显式声明的 PyPI 笔名。仓库文档层面的 12 处路径命中已逐类定性（5 处真实历史证据保留、2 处是「扫描模式串」自指、2 处合成、1 处误报、2 处本轮文档引用）。唯一新增可登记项是提交作者邮箱随 commit 对象公开，定性 **P3 非阻断**，不在冻结轮处置。


## 6. 冻结面确认（未被发布阶段改动的部分）

| 面 | 状态 |
|---|---|
| `rules/`（ED001–ED010）、`schema.py`、`audit.py`、`scanner.py`、`provenance.py` | v0.1 发布点 `e17ab18` 至今 **0 改动**（`git diff --name-only e17ab18..HEAD --` 上述路径为空） |
| 四个验收 adapter（`gmmvi` / `torchssl` / `crda` / `generic`） | 同上，0 改动 |
| v1 新增面 | `src/experiment_doctor/v1/**` 15 个 .py + `adapters/captured.py` 全为新增；`adapters/__init__.py`、`cli.py` 为加法接线 |
| `schema_version` | 三处常量恒为 `"1.0"`（`v1/lock/schema.py`、`v1/run/schema.py`、`v1/verify/schema.py`），由 `tests/test_v1_lock_capture.py`、`tests/test_v1_run_capture.py` 锁定 |
| 真实项目黄金证据 | 未重跑（任务书边界）；沿用 21/21、46/46、25/25、19/19 与四份输出 sha256 基线 |

## 7. 结论

**v1.0.0 公开版本稳定**：远端与本地零漂移、tag 与 release commit 一致、三个来源的发行物哈希一致、门禁与发布前逐项相同、工作树 clean、冻结面零改动。P0 = 0，release-blocking P1 = 0，本轮新增 0 项。

*交接入口：`docs/v1/V1_HANDOFF_REPORT.md`（七节）；发布过程记录：`docs/v1/V1_RELEASE_REPORT.md`；版本决策：`docs/v1/V1_RELEASE_FINAL_REPORT.md`。*
