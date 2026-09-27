# Experiment Doctor v1.0.0 — 正式发布报告（Public Release Execution）

- 日期：2026-09-27
- 阶段：Public Release Execution。边界：不改源码逻辑、不新增 schema/rule/adapter、不重跑大型真实 acceptance、不引入 agent/framework、不修非阻塞问题；发现阻断问题即停
- 上一份：`V1_RELEASE_FINAL_REPORT.md`（RC Final，判定 release-ready）
- 结果：**v1.0.0 已公开发布完成**。GitHub Release 与 PyPI 双上线，Trusted Publishing（无 token / 无 twine），发布后全新 venv 复验通过
- 结论计数：**P0 = 0**；**release-blocking P1 = 0**（发布全程未出现需要中途修复的阻断缺陷；两处需要授权的中途决策见 §8）
- 记法：`<repo>` = 本仓库 git toplevel；`<parent>/` = 仓库根同级目录

---

## 1. 发布身份

| 项 | 值 |
|---|---|
| release commit | `fb3a24200a56724816906018a60c4a54b6149ab1`（`ci: point the publish workflow's artifact check at 1.0.0`） |
| RC Final 判定的 release-ready commit | `772501c2c1c9bbc6a327c9b1bdf927cb1468e4c8` |
| 两者关系 | 仅相差第 8 节所述的一笔 **workflow 字面量改动**（`.github/workflows/publish-pypi.yml`，5 行）；`src/`、`tests/`、schema、rules、adapters 在两者之间**零改动** |
| tag | `v1.0.0`，**annotated**（`git cat-file -t` = `tag`），tag object `6e85a56a6609c52f7661fea57b84188c3469df41` |
| tag message | `Experiment Doctor 1.0.0` |
| `git rev-parse v1.0.0^{}` | `fb3a24200a56724816906018a60c4a54b6149ab1` == release commit ✓ |
| 分支 | 本地与远端均为 **`master`**（任务书写作 "main"；本仓库从未有 `main`，未改名、未 force push、未 rebase、未 squash） |
| 上一版基线 | tag `v0.1.0` → `7c9e550`；PyPI `experiment-doctor==0.1.0`（仍在册，未受影响） |

## 2. Step 1 预检（只读）

| 检查 | 结果 |
|---|---|
| `git status --porcelain` | 空 ✓ |
| HEAD | `772501c…` ✓ 与任务书一致 |
| `v1.0.0` tag | 本地 `git tag --list "v1.0.0*"` 空、远端 `git ls-remote --tags` 空 ✓ 不存在 |
| origin | `https://github.com/xihaian251/experiment-doctor.git` ✓；`git ls-remote` 显示远端仅 `refs/heads/master` = `e17ab18` |
| `dist/` 内容 | wheel 132,806 B / sdist 147,125 B；wheel 内 `METADATA` = `Name: experiment-doctor` + `Version: 1.0.0`；当时哈希 `686226b2…` / `24731c8e…`（本地 Windows 构建） |

预检本身无失败项。发现**两个事实**并据边界条款处置：远端分支名为 `master`（非 `main`，非阻断，照 push 当前分支执行）；`publish-pypi.yml` 硬编码 `0.1.0` 四处（**阻断 Step 5**，处置见 §8 Q1）。

## 3. Commit 推送与 tag

```
git push origin master        e17ab18..fb3a242  master -> master   （9 笔 commit 全部上线）
git rev-parse HEAD            fb3a24200a56724816906018a60c4a54b6149ab1
git ls-remote origin refs/heads/master   fb3a24200a56724816906018a60c4a54b6149ab1   ← 一致 ✓
git tag -a v1.0.0 -m "Experiment Doctor 1.0.0"
git push origin v1.0.0        * [new tag] v1.0.0 -> v1.0.0
git push 内容                 本地领先 origin 的 9 笔全部上线（v1 主体 feat/test/docs + RC2 报告 + 版本 + workflow + 两份 RC 文档）
```

凭据取自 Git Credential Manager（`git credential fill`，仅取 `password=` 字段入 shell 变量、用后 `unset`，未写入任何文件或 URL；`GCM_INTERACTIVE=never GIT_TERMINAL_PROMPT=0`）。

## 4. GitHub Release

| 项 | 值 |
|---|---|
| URL | https://github.com/xihaian251/experiment-doctor/releases/tag/v1.0.0 |
| release id / tag / title | `397662215` / `v1.0.0` / `Experiment Doctor v1.0.0` |
| 类型 | 公开仓库（`private: false`）、`draft: false`、`prerelease: false` |
| `published_at` | 2026-09-27T13:32:34Z |
| Release notes | 仅任务书五行：v1.0.0 stable release / capture-first experiment evidence pipeline / lock/run/verify workflow / evidence-backed audit integration / validated against GMMVI, TorchSSL, CRDA |
| 禁用词自查 | notes 不含 AI agent / automatic improvement / trust score / capability ranking（API 回读 `body` 逐字核对） |

### 资产（最终在册）

| 资产 | id | 字节 | GitHub 服务端 sha256 digest | 上传时间 |
|---|---|---|---|---|
| `experiment_doctor-1.0.0-py3-none-any.whl` | 593010605 | 132,523 | `2bf8aa04a3b1ee8f065ea9d4c0a79cd13c958b75a7bdd36941e7bcb6705a56b2` | 2026-09-27T13:43:27Z |
| `experiment_doctor-1.0.0.tar.gz` | 593010639 | 144,788 | `6c4606aeb278949ca59f3ea9b0b2aeee88ad7039eda991b8d5d436fec83eda24` | 2026-09-27T13:43:28Z |

两行 digest 与 PyPI 登记的 sha256 **逐字符相同**（这是 §8 Q2 处置后的结果；首次上传的是本地构建 `686226b2…` / `76265fb7…`，已被替换）。

## 5. PyPI（Trusted Publishing）

| 项 | 值 |
|---|---|
| 项目页 | https://pypi.org/project/experiment-doctor/ |
| 版本页 | https://pypi.org/project/experiment-doctor/1.0.0/ |
| 发布方式 | 仅 `workflow_dispatch` 触发既有 `.github/workflows/publish-pypi.yml`；**未使用** API token、`.pypirc`、`twine upload`、手动密码 |
| workflow | `publish-pypi.yml`，run id `36322803984`，https://github.com/xihaian251/experiment-doctor/actions/runs/36322803984 |
| run 结果 | `completed / success`，attempt 1，created 13:33:23Z → updated 13:33:55Z |
| job 步骤 | `Verify clean tree` / `Build wheel + sdist` / **`Verify exactly two artifacts and version 1.0.0`** / `Publish to PyPI` 全部 success |
| environment / permissions | `environment: pypi`；`permissions: id-token: write`（workflow 文件既有配置，本轮未改） |
| PyPI 登记 | wheel 132,523 B sha256 `2bf8aa04…` @ 2026-09-27T13:33:49Z；sdist 144,788 B sha256 `6c4606ae…` @ 13:33:51Z |
| releases | `['0.1.0', '1.0.0']`；`info.version`（latest）= **1.0.0** |
| 元数据 | `requires_python >=3.11`；deps `pydantic>=2.5 typer>=0.12 PyYAML>=6.0`；`License-Expression: Apache-2.0`；`Summary` 仍为 "Read-only …"（L9 已知，本轮按边界不修） |
| CI 前置 | 发布前 `CI` run `36322720059`（push 事件，`fb3a242`）已 `success`：`quality (3.11)` / `quality (3.13)` / `build` 三 job 全绿 |

### 5.1 上传/下载一致性核对

对 PyPI 上的两个文件做**逐成员**比对（下载后与本地 Windows 构建对照）：

- sdist：文件集合完全相同；18 个成员内容不同，**差异全部为行尾**（LF vs CRLF）。
- wheel：成员集合完全相同；除 `RECORD`（因其哈希的行尾成员而随之不同）与 `WHEEL`（`Generator: setuptools (84.0.0)` vs 本地 `(80.9.0)`）外，其余差异亦**全部为行尾**。
- 结论：**代码与文档内容零差异**，差异来源是 CI 在 Linux 检出 LF、本机工作树为 CRLF，以及 setuptools 版本字样。据此（经人工确认）把 Release 资产换成 PyPI 那一份，使两处公开物的哈希一致。

## 6. 发布后复验（Step 6）

全新隔离 venv（**不**继承系统 site-packages），`pip install --no-cache-dir experiment-doctor==1.0.0`：

| # | 检查 | 结果 |
|---|---|---|
| 1 | `import experiment_doctor; __version__` | **`1.0.0`** ✓ |
| 2 | `__file__` 来源 | `<repo>/tmp/pypi_venv/Lib/site-packages/experiment_doctor/__init__.py` ✓ 非源树、非 editable（安装链含真实依赖：pydantic 2.13.5 / typer 0.27.2 / PyYAML 6.0.3 等 15 包） |
| 3 | `pip check` | `No broken requirements found.` ✓ |
| 4 | `experiment-doctor --help` | 7 命令全在册：`scan audit rules adapters init run verify` ✓ |
| 5 | 最小 synthetic smoke（在**仓库外** `<parent>/pypi_smoke_100`） | `init` → `run -- python train.py --seed 7` → `verify` → `audit . -o out` 全部退出 0 |
| 6 | verify | V001–V006 **全 PASS（6/6）** ✓ |
| 7 | audit | `adapter=captured families=1 runs=1 rules=6 fail=0` ✓ |
| 8 | 两扇门纪律 | lock `randomness.seed=CONFIRMED` 而 `execution.command=UNKNOWN`（故意未给 `--command`）；`run` 才记 `execution.command=CONFIRMED`；`termination: SUCCESS` 来自 `wait()` |
| 9 | 无源码 import | 运行目录在仓库外且 `PYTHONPATH` 未设，链路只读 site-packages 副本 ✓ |

**一次有价值的不一致及其归因**：smoke 目录**不是 git 仓库**，故 audit 给出 `ED003 INCONCLUSIVE`（`measurements.commit_status = UNKNOWN`）、`rule_inconclusive=3`，与仓库内 demo 的 `ED003 PASS` 不同。设置对照组：`git init` + 一次 commit 后重跑同一条链，PyPI 安装副本立刻给出黄金向量 `ED001 NOT_APPLICABLE / ED002 PASS / ED003 PASS / ED004 INCONCLUSIVE / ED009 INCONCLUSIVE / ED010 PASS`，`verify` 仍 6/6 PASS。→ 差异完全由"没有可观测的仓库"解释，工具**没有**把缺失事实填成 PASS，也没有因此报错（`UNKNOWN 不是错误`）。

**传播延迟事实**：`publish` 成功后立刻 `pip install …==1.0.0` 失败一次（`from versions: 0.1.0`），约 2 分钟后同一命令成功；期间 `pypi.org/simple/` 已列出 1.0.0 而 `/project/` 页的 latest 仍显示 0.1.0。属 PyPI 边缘缓存行为，非发布缺陷。

## 7. 最终 git 状态

| 项 | 值 |
|---|---|
| 远端 `refs/heads/master` | `fb3a242…`（+ 本报告的 docs commit，见下） |
| 远端 tags | `v0.1.0`（→ `7c9e550`）、**`v1.0.0`**（→ `fb3a242`） |
| 本地 HEAD | 与 `origin/master` 一致，`git status --porcelain` 为空 |
| 发布链上的 tag 位置 | `v1.0.0` 钉在 `fb3a242`；其后的 docs commit 仅改本文件，不影响发行载荷（`docs/` 不进 wheel/sdist） |
| 工作区杂项 | `dist/` 现存放与 PyPI 一致的那一对文件；本地 Windows 构建的原件移到 `tmp/gh/local_build/`（`tmp/` 已 gitignore，未进入任何 commit） |

## 8. 中途需要授权的两次决策

| # | 情形 | 处置 | 是否越界 |
|---|---|---|---|
| Q1 | `publish-pypi.yml` 四处硬编码 `0.1.0` → Step 5 必红；而 token/twine 均被禁止，不动该文件即无法发布 | **停手并请示**；获授权后做**最小字面替换**（4 处 + 步骤名，共 5 行），单独一笔 `ci:` commit（`fb3a242`），随后 push/tag/发布 | 未改任何源码逻辑；release commit 因此从 `772501c` 前移一笔，已在 §1 登记 |
| Q2 | Release 资产与 PyPI 产物哈希不同（根因经 §5.1 证明为行尾 + setuptools 版本字样） | 先证明内容零差异，再**请示**；获授权后删旧资产、上传 PyPI 同字节文件，两套哈希全部登记 | 不改已发布内容；Release URL 与 tag 不变 |

## 9. 已知限制（发布不改变其状态）

RC Final §6 的 L1–L11 全部原样有效（无 metric 提取、无训练结论、无 composite 分数、capture forward-only、无 hardware/cuda、无 tracker 集成、`run` 会真实执行命令、sdist 不可字节复现等）。本次发布**新登记**两条：

| # | 事实 | 分类 |
|---|---|---|
| L12 | PyPI 与 GitHub Release 的产物由**不同构建环境**产出（CI/Linux/setuptools 84.0.0 vs 本机/Windows/setuptools 80.9.0），字节不同而行尾归一后等价；现资产已取 PyPI 那份，故两处哈希一致，但复现他人构建须自带等价环境 | 已缓解，登记为事实 |
| L13 | `Summary` / 包 docstring / CLI 帮助文案仍为 v0.1 措辞（"Read-only …"、"Experiment Doctor v0.1"），现已随 1.0.0 出现在 PyPI 项目页 | 非阻断，属 §6 的 D2/L9，未在本轮修 |

## 10. 发布闭环核对表

| 目标 | 状态 |
|---|---|
| GitHub repository | ✓ 9 笔 commit 上线，`master` = `fb3a242` |
| annotated tag | ✓ `v1.0.0` → `fb3a242`，已推送 |
| GitHub Release | ✓ 公开、非 draft、非 prerelease，notes 仅 5 行，2 个资产哈希与 PyPI 一致 |
| PyPI Trusted Publishing | ✓ run `36322803984` success；`1.0.0` 在册并成为 latest；无 token/twine |
| 发布后复验 | ✓ 全新 venv：版本 / pip check / CLI / init-run-verify-audit / V001–V006 / captured adapter |
| 边界 | ✓ 未新增 schema/rule/adapter、未改判定逻辑、未重跑大型 acceptance、未引入 agent/framework、未开 v1.1 |

---

*发布终点：Experiment Doctor 1.0.0 已在 GitHub 与 PyPI 同时公开可用；P0 = 0，release-blocking P1 = 0；未进入 v1.1，未处理 L9/L13 文案与非阻塞项。*
