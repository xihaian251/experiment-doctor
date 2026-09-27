# release/v1.0.0 — 验证报告索引（VALIDATION_REPORTS_INDEX）

- 生成日期：2026-09-27（Post-Release Freeze & Handoff 阶段 Step 2 产物）
- 用途：给「拿着 v1.0.0 发行物、但拿不到本项目对话历史」的人一张证据地图。**权威文档在 `docs/v1/`**，本目录只保存哈希清单、发布报告冻结副本与本索引，不复制源码、不复制用户数据、不保存环境变量。
- **哈希口径（先读这段再比对）**：下表哈希一律取 **git blob 的字节**（LF 规范化后的入库内容），大小同。Windows 工作树里 `git config core.autocrlf=true` 会把部分 Markdown 检出为 CRLF，此时**直接对文件算 sha256 会得到不同的值**——那不是内容漂移。校验命令见 §4。
- 表中 `sha256` 只印前 16 位（人工核对够用）；需要全量请用 §4 的命令现算。
- 自指说明：本文件不索引自身（写索引时它尚不存在，且写完即变）。

## 1. 发行物哈希（与 PyPI / GitHub Release 三方一致，二进制不受 EOL 影响）

见同目录 `SHA256SUMS.txt`（全文 sha256，可直接 `sha256sum -c` 校验）：

| 文件 | 字节 | sha256 |
|---|---|---|
| `experiment_doctor-1.0.0-py3-none-any.whl` | 132,523 | `2bf8aa04a3b1ee8f065ea9d4c0a79cd13c958b75a7bdd36941e7bcb6705a56b2` |
| `experiment_doctor-1.0.0.tar.gz` | 144,788 | `6c4606aeb278949ca59f3ea9b0b2aeee88ad7039eda991b8d5d436fec83eda24` |

发布通道为 GitHub Actions Trusted Publishing（run `36322803984`），release commit `fb3a242`，annotated tag `v1.0.0`（tag object `6e85a56`）。

## 1.5 本目录自身内容

| 文件 | blob 字节 | sha256 前 16 | 备注 |
|---|---|---|---|
| `SHA256SUMS.txt` | 204 | `3d19a91de230c53c` | 工作树与 blob 相同（仅 2 个 LF） |
| `V1_RELEASE_REPORT.md` | 12,303 | `cfc7b266a8bffc43` | 与 `docs/v1/` 原件**同一 blob**（工作树里两者都是 CRLF 的 12,456 B） |
| `VALIDATION_REPORTS_INDEX.md` | — | — | 本文件，不列自身哈希 |

`ls release/v1.0.0` 应与上表一致：**只有这三份**。

## 2. 证据链文档（按「先读哪份」排序）

| # | 路径 | blob 字节 | sha256 前 16 | 工作树是否等于 blob | 这份记的是什么 |
|---|---|---|---|---|---|
| 1 | `docs/v1/V1_HANDOFF_REPORT.md` | 20,235 | `af30647693f05999` | 相同 | **交接入口**：身份 / 冻结架构 / 证据 / 稳定接口 / limitation / 未来边界 / 可复现命令 |
| 2 | `docs/v1/FINAL_RELEASE_STATE.md` | 11,646 | `d9eb07ad35677a7e` | 相同 | 冻结快照：远端零漂移、三方哈希一致、门禁复跑，**§5 为安全终审计**（凭据 / 绝对路径 / 个人标识分类登记） |
| 3 | `docs/v1/V1_FINAL_STATUS.md` | 8,522 | `0df69564da1e2652` | 相同 | v1.0.0 保证什么、刻意不做什么、稳定接口清单、具名 limitation |
| 4 | `docs/v1/V1_RELEASE_REPORT.md` | 12,303 | `cfc7b266a8bffc43` | **不同**（CRLF，12,456 B / `96bded1694d863f7`） | 发布执行记录：preflight → push → tag → GitHub Release → PyPI → 发布后验证，含两次人工授权决策 Q1/Q2 |
| 5 | `docs/v1/V1_RELEASE_FINAL_REPORT.md` | 16,444 | `2623dd5474932578` | 相同 | 版本决策（为何 1.0.0 而非 0.2.0）+ 发布前四门禁 + 提交历史 + 包哈希 + 已知限制 |
| 6 | `docs/v1/V1_RELEASE_CANDIDATE_RC2_REPORT.md` | 18,232 | `29c068d5d08e8016` | 相同 | RC2：blocker 处置、文档迁入 `docs/v1/`、绝对路径分类、待决 D1–D7 |
| 7 | `docs/v1/V1_RELEASE_CANDIDATE_REPORT.md` | 16,991 | `60ad4b8aa84baa91` | **不同**（CRLF，17,176 B / `14c69e6ab87ef31a`） | RC1：只读发布边界审查（不改代码） |
| 8 | `docs/v1/V1_RELEASE_CHECKLIST.md` | 14,903 | `61abe2bc6bcc7e6c` | **不同**（CRLF，15,033 B / `a5431b2cc48a81c0`） | 发布台账（逐项勾验） |

## 3. 设计与阶段报告（v1 功能如何长成这样）

| 路径 | blob 字节 | sha256 前 16 | 阶段 |
|---|---|---|---|
| `docs/v1/EXPERIMENT_DOCTOR_V1_DESIGN.md` | 26,110 | `cf53143e58bb1357` | 设计：capture-first、两道门、UNKNOWN 纪律 |
| `docs/v1/EXPERIMENT_DOCTOR_V1_IMPLEMENTATION_PLAN.md` | 22,042 | `db9a9fb9f9cd76d9` | 实施计划（Phase 1–5 划分） |
| `docs/v1/PHASE1_LOCK_CAPTURE_REPORT.md` | 13,896 | `c8b17af11e3bb4d9` | lock schema + capture 层 |
| `docs/v1/PHASE2_RUN_CAPTURE_REPORT.md` | 8,459 | `0a8619daf31a8454` | `run` + evidence bundle |
| `docs/v1/PHASE3_VERIFY_REPORT.md` | 8,488 | `d50abc0c7d0ec31a` | V001–V006 确定性验证 |
| `docs/v1/PHASE4_AUDIT_INTEGRATION_REPORT.md` | 14,680 | `3ac90ff72f9f9d75` | captured adapter 接入 |
| `docs/v1/PHASE5_FINAL_VALIDATION_REPORT.md` | 18,776 | `2655dc625cafcc6e` | 端到端 golden + 四套真实回归 + 安全边界审计（`21/21`、`46/46`、`25/25`、`19/19` 及输出 sha256 基线见其 `:138-144`） |

§2 与 §3 的其余条目工作树与 blob 一致（本轮实测），故不必单列 CRLF 变体值。

## 4. 校验方法与不变性说明

```bash
# 权威口径：对 git blob 求哈希（跨平台一致）
git cat-file blob HEAD:docs/v1/V1_HANDOFF_REPORT.md | sha256sum

# 若要在 Linux / CI（autocrlf=false 或 input）里比对工作树文件，直接：
sha256sum docs/v1/V1_HANDOFF_REPORT.md      # 与上式相同
# 在 Windows + core.autocrlf=true 的检出里，Markdown 会变 CRLF，
# 此时请先规范化再比：
python - <<'EOF'
import hashlib, pathlib, subprocess
for f in ["docs/v1/V1_RELEASE_REPORT.md", "docs/v1/V1_HANDOFF_REPORT.md"]:
    blob = subprocess.run(["git","cat-file","blob",f"HEAD:{f}"], capture_output=True).stdout
    print(f, len(blob), hashlib.sha256(blob).hexdigest())
EOF
```

- 上表哈希是**冻结时点**（HEAD = 本目录入库那一笔）实测值。这些报告属历史事实证据：后续任何一轮都不得就地改写，只能追加新文件并在新文件里说明差异。
- 冻结面：`git diff --name-only e17ab18..HEAD -- src/experiment_doctor/schema.py src/experiment_doctor/rules src/experiment_doctor/audit.py src/experiment_doctor/scanner.py src/experiment_doctor/provenance.py src/experiment_doctor/adapters/gmmvi.py src/experiment_doctor/adapters/torchssl.py src/experiment_doctor/adapters/crda.py src/experiment_doctor/adapters/generic.py` 输出为空（v0.1 核心与四个验收 adapter 自 v0.1.0 发布线起 0 改动）。
- 本目录**不含**：源码、wheel/sdist 二进制、用户项目 artifact、环境变量导出件、token 或凭据。安全终审计已覆盖本目录全部文件，结论见 `docs/v1/FINAL_RELEASE_STATE.md` §5。
