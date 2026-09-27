# Experiment Doctor — Schema Refinement Report

任务：修复 v0.1 规则验收中被两个真实项目证明存在的两个 P1 schema 限制（ruleset report §22 条 1、2），
使 provenance 表达更科学。本轮为 schema refinement，不是功能扩展：规则仍为 ED001–ED010 十条，
adapter 与 scanner 未动，未新增命令、评分或结论性标签。
基线 HEAD `b691752`；本轮提交 `839f748`（refactor）与紧随其后的 test 提交。

## 1. Motivation

跨项目验收把两个问题从"推测"变成了"实测记录"：

- **P1-a**：`ExperimentRun.environment` 一字段两义。GMMVI 用它装任务环境（`breast_cancer`，
  引到 config 的 `experiment_id`），TorchSSL 用它装仓库声明（`environment.yml` 的 conda pins），
  而 ED010 问的是第三个东西：run 自己有没有记录它运行时的软硬件环境。schema 无法表达
  "declared environment exists 但 runtime environment unknown"。
- **P1-b**：仓库级依赖声明（`requirements.txt`、`environment.yml`、SLURM 模板）只是普通文件，
  没有正式的 provenance 建模：无法表达"该 artifact 属于 project、声明 dependencies、
  不绑定任何 run、未被 runtime evidence 验证"。

## 2. Previous limitation

- TorchSSL 的 `declared_environment_files` 实测为 0，而声明文件真实存在（scanner 以日志目录为根），
  读者无法从测量值核实声明。
- GMMVI 的证据字符串可能指向任务名，读者以为在看版本（ruleset report §22 条 1）。
- ED010 的两个终态（声明存在 / 记录缺失）挤在同一个 INCONCLUSIVE 里，没有可引用的结构区分。

## 3. Schema changes

`src/experiment_doctor/schema.py`，+178 行，全部为加法（无任何旧字段语义改动）：

| 新概念 | 内容 |
|---|---|
| `RuntimeEnvironment` | `python_version` / `framework_versions` / `cuda_version` / `hardware` / `os`，全部 `ProvenanceField`，加 `source_artifacts`；`version_map()` 只收版本性方面，硬件与 OS 名不参与制造冲突 |
| `DeclaredEnvironment` | `artifact_id` / `artifact_type`（`requirements`/`environment_yaml`/`conda_yaml`/`dockerfile`/`slurm_template`/`unknown` 枚举）/ `source_path` / `declared_dependencies: ProvenanceField[dict]` / `provenance` |
| `ArtifactRef.artifact_role` | 封闭枚举 `ArtifactRole`（8 值，含 `DECLARED_ENVIRONMENT`），`None` 表示未分类；不接受自由字符串（pydantic 枚举校验拒绝） |
| `RunEnvironmentBinding` + `EnvironmentRelationship` | `run_id` / 可选 runtime / 可选 declared / `relationship_status ∈ {MATCHED, CONFLICTING, ONLY_DECLARED, ONLY_RUNTIME, UNKNOWN}` |
| `relate_environment_evidence()` | 只有双方对同一包都给出版本且一致才 `MATCHED`；无共享键、空声明、缺失侧一律不升级 |
| 挂载点 | `ExperimentRun.runtime_environment = None`；`ExperimentProject.declared_environments = []` |

`DeclaredEnvironment` 不能自动升级为 `RuntimeEnvironment`：ED010 只认 run 本地引用
（`_slot_is_run_local`），声明引用来的一切证据都落在 declared 侧。

## 4. Backward compatibility

- 所有新字段均为可选、默认惰性（`None` / 空表），旧 JSON 记录逐字可读——由
  `test_environment_schema_additions_keep_old_json_readable` 显式验证（删去三个新键后
  `model_validate` 通过）。
- 旧字段（`environment` 标量、`compute_budget`、`ArtifactType`）一个未删、一个未改语义。
- 两个 legacy acceptance 的编号与断言未动（见 §7、§8）；`rule_acceptance.json` 重跑后与已提交
  版本**字节一致**（见 §9）。
- 无新增综合评分、verdict 或置信度数字。

## 5. ED010 changes

规则 ID、标题、entity、十条总数全部不变；只改 `rules/environment.py` 内部判定。
`experiment-doctor rules` 的 registry 测试仍断言恰好 ED001–ED010。

| 状态 | 新语义 |
|---|---|
| PASS | 存在 run 本地 runtime 证据（标量被 run 自身 artifact 引证，或结构化 slot 引到 run 文件），且无冲突；硬件缺失仍记 limitation 不隐藏 |
| FAIL | ① 互斥 runtime 记录（原有 `CONFLICTING` 分支保留）；② runtime 记录与仓库声明在同一包版本上明确矛盾（新增，Case C） |
| INCONCLUSIVE | 只有 declared 证据：仓库声明存在 / 标量值引到 run 外文件（原文案保留）/ slot 值全部引到仓库文件（requirements、SLURM、Dockerfile 均不能造 PASS） |
| NOT_APPLICABLE | 新增：整个项目对 environment 零证据（无 run 记录、无 slot、无声明）——问题无从成立，不是通过 |

行为面**唯一**的刻意变化是零证据分支 INCONCLUSIVE→NOT_APPLICABLE；两个已验收项目都有声明存在，
该分支在真实数据上不可达（见 §7–§9 全等结果）。其余测量键原样保留，新增
`environment_relationship` 与 `runtime_evidence_recorded` 两个观测值。不因版本缺失而 FAIL：
空声明、不相交键、无法比较的标量字符串一律不判冲突。

## 6. Synthetic validation

`tests/test_rules.py` 净增 9 测试（95→**104 passed**），原 ED010 四测试语义保持：

- Case A：只有 `environment.yml` → INCONCLUSIVE，`relationship=ONLY_DECLARED`；
- Case B：log `torch=2.0` + 声明 `torch=2.0` → PASS，`relationship=MATCHED`；
- Case C：log `torch=2.0` + 声明 `torch=1.7` → FAIL，`relationship=CONFLICTING`；
- Case D：无任何环境 artifact → NOT_APPLICABLE（替换原零证据 INCONCLUSIVE 测试）；
- 防火墙 9→**13** 条：新增 requirements→执行依赖 PASS、SLURM→真实硬件 PASS、
  Dockerfile→真实容器 PASS 三条禁入路径，外加 "MATCHED 不得从缺版本/不相交推断"；
- `artifact_role=DECLARED_ENVIRONMENT` 计入 `declared_environment_files`（P1-b 词汇落地）；
- 兼容性测试（§4）。

## 7. GMMVI regression

`scripts/run_gmmvi_acceptance.py` 本轮跑恰好一次：**21/21 passed**，
`reported_vs_recomputed: match 36 / mismatch 0`，输出
`tmp/acceptance_gmmvi_schema_refinement.json`。
3,483 runs / 205 families 规模不变；rule 层 ED010 仍 INCONCLUSIVE ×3,483
（`source_attached_to_run=false`、`declared_environment_files=3`、
`environment_relationship=ONLY_DECLARED`，任务名与声明均被拒绝为 runtime 证据）。

## 8. TorchSSL regression

`scripts/run_torchssl_acceptance.py` 本轮跑恰好一次：**46/46 passed**，输出
`tmp/acceptance_torchssl_schema_refinement.json`。检查
`environment_declared_not_confirmed` 仍过：adapter 未动，`environment` 仍 SUPPORTED 引到
`environment.yml`，6 runs 全部 INCONCLUSIVE——声明永不 PASS 运行时环境。

## 9. Rule acceptance regression

`scripts/run_rule_acceptance.py` 本轮跑恰好一次：**19/19 passed**，且重跑产物与已提交的
`rule_acceptance.json` **字节一致**（git 无 diff）——逐规则分布、全部 10 条语义断言零漂移，
包括 `gmmvi_ed010_environment_declared_not_recorded` 与
`torchssl_ed010_environment_is_not_recorded_by_the_run`（仍 [INCONCLUSIVE]）与
ED008 在 TorchSSL 上的唯一真实 FAIL。五条本地门禁同轮全绿：
pytest 104、ruff check、format 55 files（53 + 本轮新增 2 个 md，ruff 同时检查 markdown 代码块）、
mypy 39 source files、rules/ 项目名 grep 0 命中。

## 10. Remaining limitations

1. **注册是 adapter 的活，本轮 adapter 冻结**：没有任何 v0.1 adapter 会填
   `runtime_environment` / `declared_environments`，因此 MATCHED/CONFLICTING 分支在两个真实
   项目上尚不可达，目前仅由合成测试证明语义正确。P1-b 的"登记为项目 artifact"只完成了词汇表，
   登记动作需下一轮显式批准改 adapter。
2. GMMVI 的 `environment` 标量仍装着任务名：schema 侧歧义已由新类型终结，数据侧的改写
   （拆槽或停止写入）需要 adapter 变更，未在本轮范围。
3. 版本比较是规范化（小写、去空白）后的精确串匹配，不解析 PEP440/semver：`1.7` 与 `1.7.1`
   会判冲突——方向偏保守但存在名义冲突风险，登记于此。
4. 标量 runtime 字符串与 typed 声明之间不做比较（不解析自由文本），关系保持 UNKNOWN。
5. ED001–ED009 未消费新词汇；本轮只有 ED010 的判定逻辑改变。
6. 消费方若统计五态分布，需开始处理 ED010 的 NOT_APPLICABLE（severity INFO）。
