# Phase 3 报告：Verify（evidence bundle 确定性验证）

- 日期：2026-09-27
- 范围：v1.0 实施计划 Phase 3。前置：Phase 1/2（两份 PHASE 报告已复核：
  lock_hash / run_hash 契约、ProvenanceField、UNKNOWN 纪律、bundle 四件套）
- 状态：**完成**。未进入 Phase 4（audit integration）；未 commit；未发布。
- 结果速览：新增 19 个测试；全量回归 `180 passed, 1 skipped`
  （v0.1 原 118+1、Phase 1 21、Phase 2 22 **全部零漂移**）；ruff check /
  format --check（80 files）/ mypy（61 files）全绿；真实子进程
  `init → run → verify` 端到端 smoke 六项全 PASS。
- 过程说明：消息挂载的 crewai / autogpt / autoresearch / creative-thinking
  四个 skill 与任务书禁令（不创建 Agent、确定性验证）冲突，**未加载执行**。

---

## 1. Verify Schema（`v1/verify/schema.py`）

`VerificationReport`：

```
schema_version: "1.0"
bundle_identity:
    bundle_path                       # 观测
    lock_hash_expected / lock_hash_observed   # 存储声明 vs 重算观测
    run_hash_expected / run_hash_observed
checks: CheckRecord[]                 # 固定 V001–V006
```

- `CheckRecord = {check_id, status ∈ PASS|FAIL|INCONCLUSIVE|NOT_APPLICABLE,
  evidence[], message}`——任务书四态原样，无第五态。
- **结构级禁令落实**：模型里不存在 `overall_score`/`confidence`/`trust_score`
  字段；序列化文本测试断言 `"score"`/`"confidence"`/`"verdict"` 等 JSON key 永
  不出现（注意：leaf 复用的 v0.1 `ProvenanceField.confidence_note` 是证据注
  释，不是分数，测试注释已区分）。
- hash pair 的 expected/observed 仍是 `ProvenanceField`：文件读不到时如实
  UNKNOWN（校验器保证 UNKNOWN 无值），报告本身不给 bundle 打任何综合分。
- 确定性：`canonical_json()`（同 Phase 1/2 契约）+ `digest()`；两次验证同一
  bundle 输出逐字节相同（`report.digest()` 相等测试，因为 bundle 含时间戳，
  跨 bundle 的哈希必然不同——验证的是"同一输入同一输出"）。
- 报告自带 `exit_code` 属性：`1 if any FAIL else 0`。

## 2. 六个验证检查（`v1/verify/checks.py`）

| id | 检查 | 判据（全部重算/观测，无修复） |
|---|---|---|
| V001 Lock Integrity | lock 文件 | 去掉 `lock_hash` 后按 canonical 契约重算；stored≠recomputed / 不可读 / 封印一致但违反 ProvenanceField 不变式 → FAIL |
| V002 Run Reference Integrity | run.lock_reference ↔ 当前 lock | 记录的 hash ≠ bundle lock **重算** hash → FAIL；引用为 UNKNOWN → INCONCLUSIVE（缺席≠矛盾）；无可信重算值可比 → INCONCLUSIVE |
| V003 Run Hash Integrity | run 文件 | 与 V001 同契约作用于 `run_hash` |
| V004 Evidence Presence | 四件套 | JSON 缺失/不可解析 → FAIL；JSON 零字节 → FAIL；**log 零字节 → INCONCLUSIVE**（沉默运行可以合法产生空 stdout，判 FAIL 就是臆断） |
| V005 Artifact Integrity | created/modified 声明 | 逐条解析（绝对路径→bundle→project）并重算 sha256：找到且一致 → PASS 计数；**内容不符 → FAIL**；找不到 → INCONCLUSIVE，消息逐字声明"NOT read as deletion… NOT as fabrication"；无声明 → NOT_APPLICABLE |
| V006 Path Boundary | run 记录的路径声明 | stdout/stderr/lock_path/output_dir 等字段的**绝对路径**若落在 bundle ∪ 项目根之外 → FAIL；`execution.cwd` 是观测到的边界定义者、自由文本非写入声明 → 豁免 |

V006 边界裁决（设计决策，如实登记）：Phase 2 记录里唯一合法的绝对路径就是
capture 时的 `cwd`（它本身就等于项目根）；lock 侧的 cwd/dataset 绝对路径属于
**输入声明**而非 bundle 写入声明，纳入扫描会造成 shipped-bundle 场景的系统性
误报，故扫描范围限定为 run 记录的路径声明字段。该取舍写进了代码注释与本报告。

## 3. 状态语义（本层最重要的公共契约）

- `PASS`：检查执行了，声明与重算证据一致。
- `FAIL`：检查执行了，且证据**积极矛盾**（篡改、缺失的 JSON、越界写入声明）。
- `INCONCLUSIVE`：无法从 bundle 内下结论——UNKNOWN 引用、verify 时找不到的
  artifact、零字节日志。**不是错误**：单独存在时 exit 0。
- `NOT_APPLICABLE`：被检对象不存在或不构成声明（run 整体不可用、artifacts 无
  声明）。同样 exit 0。
- 任务书退出码表：全 PASS→0；有任何 FAIL→1；只有 INCONCLUSIVE→0
  （"UNKNOWN 不是错误"由 `report.exit_code` 一处实现，CLI/测试共用）。

## 4. Tamper 矩阵（`tests/fixtures/v1_verify_project/` + 19 tests）

| 任务书 | 操作 | 期望 | 实测 |
|---|---|---|---|
| T1 | clean bundle | 全 PASS | ✔ 六项 PASS（另测：报告确定性、verify 仅新增自己的两个输出且 lock/run/log 字节不变） |
| T2 | 改 lock 内容（seal 不重算） | V001 FAIL | ✔ 且 **V002 同时 FAIL**——run 记录的 lock hash 与改后 lock 的重算值积极矛盾（链从另一侧也被抓住）；V003 保持 PASS |
| T3 | 改 run 内容 | V003 FAIL | ✔ T3b：伪造 lock 引用并弃封印（run_hash=None）→ V002+V003 双 FAIL |
| T4 | 删 stdout.log | V004 FAIL | ✔（JSON 缺失同样 FAIL，log 零字节为 INCONCLUSIVE） |
| T5 | 删 artifact | V005 INCONCLUSIVE | ✔ exit 0；T5b：保名换内容 → V005 FAIL |
| T6 | 路径改到 bundle 外 | V006 FAIL | ✔ T6b：stderr_path 指向 `C:/Windows/...` → FAIL |
| T7 | Phase 2 bundle 兼容 | 可验证 | ✔ verify→`os.replace` 搬走 bundle→删除整个项目（只读 .git 对象需 chmod）→ 再验证：V001–V004/V006 PASS、V005 INCONCLUSIVE——哈希检查不依赖原机器 |

反推断防火墙（Step 5，逐项有测试）：
- stdout.log 写入 `accuracy=99.9 … converged` 或 `OOM, diverged` → 六项状态
  **一字不变**（verify 无 stdout 解析路径）；
- exit 0 + 零 artifact → V005 NOT_APPLICABLE，且断言任何 message 不含
  "train"（不判定训练成败）；
- UNKNOWN 永不升级成 FAIL（T2 的 UNKNOWN 引用、T5 的找不到文件均为
  INCONCLUSIVE）；
- metric 缺失不 FAIL（schema 根本没有 metric 字段）；
- 状态集合 ⊆ 四态、check 序列恒为 V001…V006。

## 5. 安全边界

- **只读验证**：verify 对 lock/run/log 四类文件只读；写操作仅
  `bundle/verify.json`、`bundle/verify.md` 两个自有输出（测试逐字节比对
  before==after + bundle 文件清单精确等于 4+2）；无自动修复、无重封印代码路
  径（`write_verify_outputs` 只写 report 自己的 dump）。
- 不修改 Phase 1/2 文件：本轮 `v1/lock`、`v1/run` 零改动；对既有代码唯一改动
  仍是 `src/experiment_doctor/cli.py` 的 docstring + import + 注册行。
- v0.1 四命令 + init/run 的 `--help` 注册测试扩展为七命令全绿。
- 凭据扫描沿用 Phase 2：`v1/` 源码 grep password/passwd/secret/token/
  credential/api_key 零命中（verify 目录纳入同一扫描）。

## 6. 仍未解决的 UNKNOWN（诚实清单）

1. **V005 的"找不到"不区分**"换了机器"与"真的没生成过"——这是 bundle 证据
   边界的固有局限，只能 INCONCLUSIVE，交给 audit/人裁决。
2. **时间戳无锚**：start/end/created_at 的可信度依赖 capture 时系统时钟，
   verify 无法重算（无外部时间源，Phase 3 禁云端）。
3. **lock 侧输入路径未扫**（§2 裁决）：dataset/config 绝对路径越界由 Phase 4
   audit 或人工处理。
4. **lock↔run 双向声明未测**（cwd 一致性、dataset 未变动）：任务书未列，本轮
   不扩规则。
5. **无签名/防重放**：篡改者若懂 canonical 契约可整体重封印（lock_hash 与
   run_hash 同时重算）；bundle 级签名被任务书明令禁止，抵御该攻击需要外部 trust
   anchor（v1.1 议题）。
6. **stdout/stderr 完整性只到"存在"**：日志内容未被哈希进 run record（只有
   artifact 有 sha256），换日志字节不会 FAIL——登记为证据面缺口。
7. **V004 与文件内路径声明的既有张力**：若 run 在项目根之外被调用（绝对路径
   日志），V006 按设计 FAIL——语义为"该 bundle 不自包含"，非 bug。

---

*Phase 3 交付终点。未 commit；未进入 Phase 4 audit integration；未发布。*
