# release/v1.0.0 — 验证报告索引（VALIDATION_REPORTS_INDEX）

- 生成日期：2026-09-27（Post-Release Freeze & Handoff 阶段 Step 2 产物）
- 用途：给「拿着 v1.0.0 发行物、但拿不到本项目对话历史」的人一张证据地图。**权威文档在 `docs/v1/`**，本目录只保存哈希清单与发布报告冻结副本，不复制源码、不复制用户数据、不保存环境变量。
- 哈希口径：`sha256` 对文件**原始字节**计算；大小单位为字节。下表最后一列为「本目录内是否有副本」。
- 自指说明：本文件不索引自身（写索引时它尚不存在）。若需校验本目录完整性，先校验其余条目，再对 `SHA256SUMS.txt` 做发行物哈希比对。

## 1. 发行物哈希（与 PyPI / GitHub Release 三方一致）

见同目录 `SHA256SUMS.txt`：

| 文件 | sha256 |
|---|---|
| `experiment_doctor-1.0.0-py3-none-any.whl` | `2bf8aa04a3b1ee8f065ea9d4c0a79cd13c958b75a7bdd36941e7bcb6705a56b2` |
| `experiment_doctor-1.0.0.tar.gz` | `6c4606aeb278949ca59f3ea9b0b2aeee88ad7039eda991b8d5d436fec83eda24` |

发布通道为 GitHub Actions Trusted Publishing（run `36322803984`），release commit `fb3a242`，annotated tag `v1.0.0`（tag object `6e85a56`）。

## 1.5 本目录自身内容清单

| 文件 | 字节 | sha256 |
|---|---|---|
| `SHA256SUMS.txt` | 204 | `3d19a91de230c53ca085d804f3e4728f830df601f0a5ecd0c1cbc12744337746` |
| `V1_RELEASE_REPORT.md` | 12,456 | `96bded1694d863f79f647c2f925ce8df0ba9f1bf660aab17881d8996ec391f42`（与 `docs/v1/` 原件逐字节相同） |
| `VALIDATION_REPORTS_INDEX.md` | — | 本文件；不列自身哈希（写入后即为自指），完整性靠上两条 + §2/§3 的文档哈希链 |

本目录**只有这三份文件**：`ls release/v1.0.0` 应与上表一致。

## 2. 证据链文档（按「先读哪份」排序）

| # | 路径 | 字节 | sha256（前 16 位） | 本目录有副本 | 这份记的是什么 |
|---|---|---|---|---|---|
| 1 | `docs/v1/V1_HANDOFF_REPORT.md` | 19,605 | `ac254c646961f74e` | 否 | **交接入口**：身份 / 冻结架构 / 证据 / 稳定接口 / limitation / 未来边界 / 可复现命令 |
| 2 | `docs/v1/FINAL_RELEASE_STATE.md` | 11,646 | `d9eb07ad35677a7e` | 否 | 冻结快照：远端零漂移、三方哈希一致、门禁复跑，**§5 为安全终审计**（凭据/绝对路径/个人标识分类登记） |
| 3 | `docs/v1/V1_FINAL_STATUS.md` | 8,522 | `0df69564da1e2652` | 否 | v1.0.0 保证什么、刻意不做什么、稳定接口清单、具名 limitation |
| 4 | `docs/v1/V1_RELEASE_REPORT.md` | 12,456 | `96bded1694d863f7` | **是** | 发布执行记录：preflight → push → tag → GitHub Release → PyPI → 发布后验证，含两次人工授权决策 Q1/Q2 |
| 5 | `docs/v1/V1_RELEASE_FINAL_REPORT.md` | 16,444 | `2623dd5474932578` | 否 | 版本决策（为何 1.0.0 而非 0.2.0）+ 发布前四门禁 + 提交历史 + 包哈希 + 已知限制 |
| 6 | `docs/v1/V1_RELEASE_CANDIDATE_RC2_REPORT.md` | 18,232 | `29c068d5d08e8016` | 否 | RC2：blocker 处置、文档迁入 `docs/v1/`、绝对路径分类、待决 D1–D7 |
| 7 | `docs/v1/V1_RELEASE_CANDIDATE_REPORT.md` | 17,176 | `14c69e6ab87ef31a` | 否 | RC1：只读发布边界审查（不改代码） |
| 8 | `docs/v1/V1_RELEASE_CHECKLIST.md` | 15,033 | `a5431b2cc48a81c0` | 否 | 发布台账（逐项勾验） |

## 3. 设计与阶段报告（v1 功能如何长成这样）

| 路径 | 字节 | sha256（前 16 位） | 阶段 |
|---|---|---|---|
| `docs/v1/EXPERIMENT_DOCTOR_V1_DESIGN.md` | 26,110 | `cf53143e58bb1357` | 设计：capture-first、两道门、UNKNOWN 纪律 |
| `docs/v1/EXPERIMENT_DOCTOR_V1_IMPLEMENTATION_PLAN.md` | 22,042 | `db9a9fb9f9cd76d9` | 实施计划（Phase 1–5 划分） |
| `docs/v1/PHASE1_LOCK_CAPTURE_REPORT.md` | 13,896 | `c8b17af11e3bb4d9` | lock schema + capture 层 |
| `docs/v1/PHASE2_RUN_CAPTURE_REPORT.md` | 8,459 | `0a8619daf31a8454` | `run` + evidence bundle |
| `docs/v1/PHASE3_VERIFY_REPORT.md` | 8,488 | `d50abc0c7d0ec31a` | V001–V006 确定性验证 |
| `docs/v1/PHASE4_AUDIT_INTEGRATION_REPORT.md` | 14,680 | `3ac90ff72f9f9d75` | captured adapter 接入 |
| `docs/v1/PHASE5_FINAL_VALIDATION_REPORT.md` | 18,776 | `2655dc625cafcc6e` | 端到端 golden + 四套真实回归 + 安全边界审计（`21/21`、`46/46`、`25/25`、`19/19` 及输出 sha256 基线见其 `:138-144`） |

## 4. 不变性说明

- 上表文档的 sha256 是**冻结时点**（HEAD `09a35cb` 之后的文档提交）实测值。这些报告属历史事实证据：后续任何一轮都不得就地改写，只能追加新文件并在新文件里说明差异。
- 副本 `release/v1.0.0/V1_RELEASE_REPORT.md` 与 `docs/v1/V1_RELEASE_REPORT.md` 经逐字节比对**哈希相同**（`96bded16…`），是快照副本而非分叉。
- 本目录**不含**：源码、wheel/sdist 二进制、用户项目 artifact、环境变量导出件、token 或凭据。安全终审计已覆盖本目录全部文件，结论见 `FINAL_RELEASE_STATE.md` §5。
