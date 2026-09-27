# Phase 4 报告：Audit Integration（captured adapter 接入 v0.1 规则引擎）

- 日期：2026-09-27
- 范围：v1.0 实施计划 Phase 4。前置：Phase 1/2/3（lock 八字段封印、run 记录与
  bundle 四件套、V001–V006 确定性验证；三份 PHASE 报告已复核）
- 状态：**完成**。未进入 Phase 5（replay）；未 commit；未发布。
- 结果速览：新增 1 个生产文件 `adapters/captured.py` + 32 个测试；全量回归
  `212 passed, 1 skipped`（v0.1 原 118+1、Phase 1 21、Phase 2 22、Phase 3 19
  **全部零漂移**）；四套验收 GMMVI **21/21**、TorchSSL **46/46**、CRDA **25/25**、
  Rule acceptance **19/19**，且与冻结 baseline **逐字节相同**；
  ruff check / format --check（82 files）/ mypy（63 files）全绿；
  真实子进程 `init → run → verify → audit` 端到端 smoke 通过。
- 改动面：`audit/` `rules/` `schema.py` `scanner.py` `provenance.py` 以及
  gmmvi/torchssl/crda/generic 四个验收 adapter **零改动**
  （`git diff --exit-code -- src/experiment_doctor/rules` 为空）。
  仓库改动只有：新增 `captured.py`、`adapters/__init__.py` 注册 2 行、
  `tests/test_packaging.py` 的 registry 期望集（详见 §7）。
- 过程说明：消息挂载的 crewai / autogpt / autoresearch / creative-thinking
  四个 skill 与任务书禁令（不创建 Agent、不新增规则）冲突，**未加载执行**。

---

## 1. Step 0：现有 audit 架构确认（只读）

读完后确定的四条契约，构成本轮设计的全部约束：

| 契约 | 出处 | 对 captured adapter 的含义 |
|---|---|---|
| adapter 协议 = `detect()` + `discover_families()` + `discover_runs()`（+ 可选 `discover_aggregations`/`project_id`/`code_repository`） | `scanner.py` | 只需实现三个方法即可被 `scan_project` 消费，不必碰 scan 流程 |
| 选路 = `detect()` 最高分者胜；`generic` 恒 0.0 兜底；`candidates.sort(..., reverse=True)` 是**稳定**排序 | `scanner.py:select_adapter` | 注册顺序决定同分胜负 → captured 注册在**最后**，1.0 平局时验收 adapter 仍胜 |
| ED003/ED004/ED010 走 `attached_to_run(run, source)`：字段的 `source.path` 必须是**该 run 自己的 artifact 之一** | `rules/base.py` | bundle 字段的 `SourceRef` 原本只有 `note` 没有 `path`（Phase 2 `observed()` 的产物），必须诚实落址，否则三条规则永远 INCONCLUSIVE |
| `ProvenanceField` 校验器：UNKNOWN 不得携带值；CONFIRMED/SUPPORTED 必须有 source；INFERRED 是启发式的天花板；规则侧证据集合 `_EVIDENCED/_RECORDED = (CONFIRMED, SUPPORTED)` | `provenance.py` | 跨层级**不允许**任何 grade 变化；`schema.py` 未开 `validate_assignment`，赋值不做运行时校验 → 转移必须手工构造正确类型 |

核心 audit 未被修改一行。

## 2. Step 1：captured adapter 的字段转移表

`src/experiment_doctor/adapters/captured.py`，定位是**翻译器而非第二观测者**：
`init`/`run` 已经对每个叶子打过 grade，adapter 只做两件事——(a) 原样携带 grade，
(b) 把引用**搬家**到"这个值写在哪个文件里"：`SourceRef(path=<bundle 文件>,
key=<block.field>, note=<原 note>)`。这与 gmmvi/torchssl/crda 对自己项目文件所
做的事在语义上同类，不是升级。

转移三件套：`_transfer`（等类型搬运，仅对已具证据的字段落址）、`_joined`
（list → 单字符串，note 里明写 "rendered from a list"）、`_epoch`
（ISO-8601 → 秒级 epoch，不可解析则保持 UNKNOWN，note 保留原字符串）。

| v0.1 字段 | 来源 | 实测等级 |
|---|---|---|
| `seed` / `seed_derivation` | lock `randomness.seed` / `.seed_source` | CONFIRMED（含 bundle 引用） |
| `code_repository` / `code_commit` / `code_dirty` | lock `code.*` | CONFIRMED；无 git 时 UNKNOWN |
| `config_source` | lock `configuration.config_files`（`, ` 连接） | CONFIRMED |
| `command` | run `execution.command`（argv，` ` 连接）；**若什么都没跑**，才退到 lock 的声明命令 | CONFIRMED |
| `start_time` / `end_time` | run `execution.*_time` → epoch | CONFIRMED |
| `compute_budget` | run `runtime.timeout_seconds` → `"wall-clock limit of {n}s set by the run wrapper"` | CONFIRMED |
| `runtime_environment.python_version/framework_versions/os` | run `environment.python_version/packages/platform` | CONFIRMED |
| `termination_cause` / `status` | 仅 `TIMEOUT` → `TIME_LIMIT` / `TRUNCATED_TIME_LIMIT` | CONFIRMED |
| artifacts | bundle 四件套自身：lock=CONFIG/CONFIG，run=SUMMARY/RESULT，两份 log=LOG/LOG | — |

**刻意不映射（全部 UNKNOWN + note 说明为何不映射）**：

1. `resolved_config`：lock 记录的是 config **路径 + 内容哈希**，从来不是合并后的
   生效值。有 hash ≠ 有 effective config → ED004 保持 INCONCLUSIVE。
2. `dataset` / `dataset_version`：`dataset.paths` 是文件列表，不是数据集身份；
   note 逐字写 "it is not a dataset identity and was not read as one"。
3. `method` / `task`（family 侧 `kind=UNKNOWN`、`declared_repetitions`、
   `membership_rule`）：bundle 里没有方法/任务名，也不能靠目录名猜 → ED001
   单 run 家族直接 NOT_APPLICABLE。
4. **lock 的 environment 块**→ 不写入 `runtime_environment`：那是进程启动**之前**
   声明的环境，不是这轮跑起来时观测到的；只有 run 记录的 environment 才映射。
5. `cuda_version` / `hardware`：bundle 里没有加速器的任何证据。
6. `metrics`：Phase 2 把 stdout/stderr 作为日志捕获且不读其中任何值，因此
   `run.metrics == []`，`audit.metrics[0].metric_names == []`——这是设计后果，
   不是漏抓。ED005–ED008 因此**产出 0 条结果**（无 aggregation 可判）。

## 3. Step 2：CLI 自动选路

`experiment-doctor audit PATH` **无代码改动**：`cli.py:audit` 一直走
`select_adapter()`，注册即生效。 captured 与 `verify` 一样只读 bundle，
`--adapter` 覆盖路径保留原样。实测（真实子进程，未装包，`PYTHONPATH=src`）：

```
init → exit 0
run  → exit 0
verify → V001–V006 全 PASS, exit 0
audit  → adapter=captured families=1 runs=1 aggregations=0
         findings=18 rules=6 rule_fail=0 rule_inconclusive=2
```

选路本身有 4 个测试：注册表内容、bundle 项目压过 generic、**非** bundle 项目
不被误捕（`select_adapter(root)[0].name == "generic"`）、直接扫描 bundle 目录本身
也能认出（`_find_bundle` 支持 `root/experiment-evidence/` 与 `root` 两种落点）。

## 4. Step 3：六条规则在 captured 数据上的实测

一次诚实捕获（有 lock + 有 run record）的规则结论：

| 规则 | 实测 | 判据来源 |
|---|---|---|
| ED001 运行身份一致性 | **NOT_APPLICABLE** | 一个 bundle 一个 run，家族不足两条，无身份可比 |
| ED002 seed 可恢复且分布 | **PASS** | seed 来自该 run 自己的 lock artifact |
| ED003 代码版本可溯 | **PASS** | commit 引用于 run 本地 artifact（搬家生效） |
| ED004 生效配置可溯 | **INCONCLUSIVE** | 无 effective config（§2 第 1 条） |
| ED009 终止原因 | **INCONCLUSIVE** | 退出码不是 `TerminationCause` 的任何一种 |
| ED010 环境可溯 | **PASS** | run record 的 environment 块、run 本地引用 |
| ED005/006/007/008 | **0 条结果** | 无 metric、无 aggregation，规则不适用 |

`findings=18`，无规则 FAIL。另有 2 个退化测试：seed 缺失 → ED002 INCONCLUSIVE；
commit 缺失 → ED003 INCONCLUSIVE（缺席 ≠ 矛盾，不编造引用）。

**终止映射的最小性**（`_CAUSE_BY_TERMINATION` 只有 1 项）：wrapper 自己施加
wall-clock 截止，所以 `TIMEOUT` 是唯一无需解释就能陈述的停止原因——它映射为
`TerminationCause.TIME_LIMIT` + `RunStatus.TRUNCATED_TIME_LIMIT`，引用落在
`runtime.timeout_status`。`SUCCESS/FAILED/INTERRUPTED` 一律保持 cause UNKNOWN，
观测到的 `TerminationStatus` **只写进 note**：进程怎么结束是关于进程的事实，
不是实验为何停下的一种原因。

## 5. Step 4：防火墙（反推断 7 项，逐条有测试）

任务书给的反例——`lock: seed=123` / `command: python train.py --seed 123` /
`stdout: accuracy=99`——**均不得**让 ED002/ED003/ED005 变 PASS：

| 测试 | 操作 | 实测 |
|---|---|---|
| `test_seed_in_the_command_string_does_not_pass_ed002` | lock 的 seed 置 UNKNOWN，argv 里塞 `--seed 123` | record 里确有 `"--seed"` 与 `"123"`，`run.command` 也确有它，但 `run.seed.value is None`、ED002 = **INCONCLUSIVE**（命令行里有 seed ≠ seed 被记录） |
| `test_metric_text_in_stdout_does_not_become_a_metric` | fixture `train.py` 打印 `accuracy=99.0 loss=0.001` 并写 `results/metrics.csv` | 两者都在盘上（测试先断言诱饵存在），`run.metrics == []`、`metric_names == []`；adapter 无任何日志解析路径 |
| `test_exit_code_zero_is_not_a_termination_cause_or_a_status` | 正常退出 0 | cause UNKNOWN、status 保持 UNKNOWN（note 记录 SUCCESS 观测） |
| `test_failed_exit_does_not_claim_a_cause` | `--exit 3` | 依旧 cause UNKNOWN（失败退出不映射成任何原因） |
| `test_only_a_wrapper_inflicted_deadline_is_a_recorded_cause` | 真超时 | 只有这一条给出 TIME_LIMIT + TRUNCATED_TIME_LIMIT，ED009 = PASS |
| `test_adapter_never_upgrades_an_evidence_grade` | 磁盘上把 seed 改成 INFERRED | 转移后仍 INFERRED，ED002 = INCONCLUSIVE（规则侧证据集只含 CONFIRMED/SUPPORTED） |
| `test_unknown_never_carries_a_value_after_transfer` | 遍历 `ExperimentRun` 全部字段 | >20 个 `ProvenanceField` 中任何 UNKNOWN 都无值（校验器 + 转移函数双保） |

配套的边界测试：`test_seal_helpers_are_unused_by_the_audit_path` 断言
`captured.py` 源码里不出现 `hash_file`/`run_hash`/`lock_hash`/`sha256`/
`verify_bundle`（audit 不重算哈希、不做篡改判定）；
`test_tampering_is_verifys_job_not_the_adapters` 证明改过内容的 bundle audit 会照
文件读（篡改归 verify 报告 FAIL），职责不混。

## 6. Step 5：零漂移证据

1. **回归**：`212 passed, 1 skipped`，其中 v0.1 原生 118+1 一字未改（唯一被动的
   既有测试见 §7，且它测的是 registry 内容而非判定逻辑）。
2. **四套验收重跑**（输入路径从各自 acceptance JSON 的 `inputs` 块读回，未猜）：
   GMMVI 21/21、TorchSSL 46/46、CRDA 25/25、Rule acceptance 19/19。
3. **逐字节比对**：四份新输出与冻结 baseline 在剥离易变键后
   `identical_to_frozen_baseline = True` **四份全真**。
4. **核心零改动**：`git diff --stat` 覆盖 `audit/ rules/ schema.py scanner.py
   provenance.py` + 四个验收 adapter → 输出为空；
   `git diff --exit-code -- src/experiment_doctor/rules` → rules/ 与 HEAD 字节相同。

## 7. 唯一改动的既有测试（如实登记）

`tests/test_packaging.py::test_adapter_registry_ships_the_four_expected_adapters`
→ 重命名为 `..._the_expected_adapters`，期望集合加入 `"captured"`（+2/-1 行，含
注释 `# v1 Phase 4: reads an experiment-doctor evidence bundle`）。

理由：该测试断言的就是"注册表里有哪些 adapter"，新增一个合法 adapter **必须**改
它，否则等于假装注册没发生。它不涉及任何判定逻辑、severity 或 schema 语义。
顺带修正了一处既有错误期待：注册名是 `gmmvi-exp3` 而非 `gmmvi`。

## 8. Step 6：质量门禁与禁令 grep

- `PYTHONIOENCODING=utf-8 PYTHONPATH=src python -X utf8 -m pytest -q`
  → 212 passed, 1 skipped
- `ruff check .` → All checks passed!；`ruff format --check .` → 82 files unchanged
- `mypy src scripts tests` → Success: no issues found in 63 source files
- 规则目录：`grep -rnE "ED01[1-9]" src/ --include=*.py` → **0 命中**（ED001–ED010
  为全部规则；severity 与判定逻辑零改动）
- 分数类禁令：`grep -rniE "overall_score|trust_score|confidence_score|
  reliability_score|composite_score" src/` → 仅 2 命中，都在
  `v1/verify/schema.py` 的 **docstring 里陈述"不存在这些字段"**；
  `captured.py` → **0 命中**（其内出现的 `confidence_note` 是 v0.1 的证据注释字段，
  不是分数）。src 内其余 `score` 字样：其他 adapter 的 `detect()` 选路分、
  `scanner.py` 的同物、以及 audit/report/rules 里"故意没有综合分"的原有散文。
- `captured.py` 无任何 ML framework import（torch/tf/jax/numpy/pandas/sklearn
  命中 0）；全文件仅 **1 处 `read_text`**，位于 `_read_model`，实际只被
  `experiment.lock.json` 与 `experiment.run.json` 两个文件名调用 → 不读日志、
  不读源码、不遍历目录树。
- 凭据扫描沿用 Phase 2 纪律：新增文件 grep password/passwd/secret/token/
  credential/api_key 零命中。

## 9. 仍未解决的 UNKNOWN（诚实清单）

1. **一个 bundle 只有一个 run**：ED001 与 ED005–ED008 在这条路径上根本没有可用
   对象（家族 size=1、无 aggregation）。跨 bundle 聚合是 Phase 5+ 的事，本轮不
   伪造"扫描全树找多个 bundle"。
2. **生效配置不可得**：lock 只有 config 路径 + hash。ED004 要 PASS 需要真正的
   merged config 捕获，v1 Phase 1 明令不解析配置文件内容。
3. **数据集身份、method、task 全缺**：bundle 里没有这些概念的位置，family
   `kind` 只能 UNKNOWN，`membership_rule` 只能 UNKNOWN。
4. **终止原因几乎总是 UNKNOWN**：wrapper 只能陈述自己制造的中断（超时）。被
   信号杀、OOM、被抢占——`INTERRUPTED` 不是"因为内存不足而停"，所以不映射。
   note 里留下观测值，判断权交给人。
5. **时间戳仍是系统时钟**：`_epoch` 只换格式不换信任源；无外部时间锚。
6. **加速器/CUDA 无证据**：Phase 2 没有捕获设备信息，ED010 的 PASS 只覆盖
   python + 包 + 平台三项，不覆盖硬件；报告里 `hardware` 恒 UNKNOWN。
7. **篡改不在本层裁决**：audit 忠实按磁盘内容产出字段（§5 最后一行），grade
   转移不校验 bundle 是否被重封印——那是 verify 的职责；两者组合才完整，单独
   跑 `audit` 的用户需自己知道这一分工。
8. **`run.metrics == []` 与"实验没有指标"是两件事**：前者是"本 bundle 未记录指标
   的机器可读形式"。审计报告里它表现为无 metric of record，不应被读成"这轮没跑
   出数"。

---

*Phase 4 交付终点。未 commit；未进入 Phase 5 replay；未发布。*
