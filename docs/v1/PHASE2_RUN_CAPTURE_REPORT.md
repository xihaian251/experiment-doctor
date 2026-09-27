# Phase 2 报告：Run Capture（`experiment-doctor run` + Evidence Bundle）

- 日期：2026-09-27
- 范围：v1.0 实施计划 Phase 2。前置：Phase 1（`PHASE1_LOCK_CAPTURE_REPORT.md`）
- 状态：**完成**。未进入 Phase 3（verify）；未 commit；未发布。
- 结果速览：新增 22 个测试；全量回归 `161 passed, 1 skipped`（v0.1 原 118+1 与
  Phase 1 的 21 全部**零漂移**）；`ruff check` / `ruff format --check`（76 files）/
  `mypy`（57 files）全绿。

---

## 1. Run Schema（`v1/run/schema.py`，新文件）

`ExperimentRunRecord`，schema_version="1.0"，canonical JSON + `run_hash`
（与 lock 同一契约：`sha256:` over sort_keys/separators/ensure_ascii=False，
`seal()`/`body()`/`compute_hash()`/`fields()` 同名同义）。所有可观测 leaf 仍是
v0.1 `ProvenanceField`，UNKNOWN 纪律由同一校验器强制。

| 块 | 字段 | Phase 2 语义 |
|---|---|---|
| `lock_reference` | `lock_hash` | 对 lock **重算 canonical hash 并核对存储值**后引用（观测，CONFIRMED）；不匹配 → value=None + UNKNOWN + "tampered" 备注 |
| | `lock_path` | 锁文件磁盘位置（观测） |
| `execution` | `command` | wrapper 实际收到的 argv 列表（"after '--'"，非推断） |
| | `cwd` | 观测的项目根 |
| | `pid` | `Popen.pid` 直接观测；未 spawn → UNKNOWN |
| | `start_time` / `end_time` | spawn 前 / wait 返回后的 UTC 时钟读数（补上了 Phase 1 留空的 lock 对应项的运行时版本） |
| | `exit_code` | **只来自 `wait()`**；未 spawn 或 kill 未生效 → UNKNOWN |
| `runtime` | `stdout_path` / `stderr_path` | wrapper 执行期间直写的日志文件（观测） |
| | `timeout_status` | 仅在真的发生 timeout/kill 时为观测值；否则 UNKNOWN（"no timeout configured"等），**永不猜测超时** |
| | `timeout_seconds` | `--timeout` 选项值；未给 → UNKNOWN |
| `artifacts` | `created_files` | 运行前后全树 sha256 diff：新出现的路径 → {path: sha256}；无变化 → UNKNOWN（"none observed"是事实而非空表造假） |
| | `modified_files` | 同上：前后都存在但哈希变化的路径 |
| | `note` | diff 方法说明 + 被删文件清单（schema 无 deleted 字段，如实放 note）+ termination 观测备注 |
| `environment` | 复用 Phase 1 `EnvironmentBlock` | run 完成时刻的**运行时**观测（与 lock 的 init 时刻观测天然分层，供 Phase 3 declared-vs-observed 对账） |
| 顶层 | `termination_status` | `SUCCESS/FAILED/TIMEOUT/INTERRUPTED/UNKNOWN`（见 §4 判定表） |
| | `run_hash` | seal 覆盖以上全部 |

**禁令落实**：没有 "training success" 字段——`SUCCESS` 的语义被逐字限定为
"process exited 0; no claim about training quality"（有测试断言该措辞进入证据）；
不存在任何读取 stdout 提取 metric 的代码路径。

## 2. CLI 行为（`v1/cli.py` 的 `run` + `cli.py` 一行加法注册）

```
experiment-doctor run [--path DIR] [--lock NAME] [--run-out NAME] [--timeout SECS] -- COMMAND [ARGS...]
```

流程：① 定位并**核验** lock（缺失 → 拒绝执行并报"run \`init\` first"，实验不启
动）；② 树快照 → 记 start_time → `Popen`（stdout/stderr 直写 `stdout.log`/
`stderr.log`）→ `wait(timeout)`；③ 记 end_time → 后快照 → 组装记录 → 写
`experiment.run.json` → 装配 evidence bundle；④ **回显 lock_hash 引用、
termination、逐字段分级**，并以 `typer.Exit(outcome.exit_code)` 镜像退出码。

- 退出码镜像（任务书硬要求）：实验 exit 1 → CLI exit 1（测试用 exit 2 验证，
  两值都非平凡）；exit 0 → 0；timeout/interrupt/未 spawn → 1/1/127。
- 负 returncode（Unix 信号）CLI 无法原生表达 → 进程退出码取 1，**精确值保留在
  record 的 exit_code 字段**（已登记，§6）。
- `--` 分隔与带空格参数经实测（click 8.3 group 解析）原样进入 argv（T6 测试）。
- v0.1 的 scan/audit/rules/adapters 实现仍逐字未动；本轮对 v0.1 文件的改动依旧
  只有 `cli.py`：docstring、两行 import、两行注册。

## 3. Evidence Bundle 结构（Step 3）

```
experiment-evidence/
  experiment.lock.json   # Phase 1 lock（副本，含 lock_hash）
  experiment.run.json    # run record（副本，含 run_hash）
  stdout.log
  stderr.log
```

原始 `experiment.lock.json`/`experiment.run.json` 保留在项目根（bundle 为汇集，
测试断言 bundle 顶层**恰好这四个文件**）。按任务书禁令：无压缩、无上传、无签名
（代码内 grep 可证，见 §5 安全测试）。

## 4. 失败模式（termination 判定表——全部为观测，无一行推断）

| 场景 | exit_code | termination_status | 证据 |
|---|---|---|---|
| 正常退出 | wait() 返回值 | 0→SUCCESS / 非0→FAILED | T1/T2 |
| 命令不存在（未 spawn） | **UNKNOWN**（没有退出码可观测） | UNKNOWN + "process never spawned" | 测试：CLI 退 127 |
| `--timeout` 到点，kill 生效 | 观测到的 kill 后状态 | TIMEOUT + kill/wait 备注 | 测试：sleep 30 vs timeout 2 |
| timeout 但 kill 未生效 | UNKNOWN + "may still be running"（**不谎称已杀**） | UNKNOWN | 代码路径 `_wait_gracefully` |
| 本地 Ctrl+C，子进程可回收 | 观测值 | INTERRUPTED | KeyboardInterrupt 分支 |
| 信号退出（rc<0）或 rc=130 | 观测值 | INTERRUPTED（"signal/SIGINT convention"备注） | `_status_for` |
| lock 被篡改（hash≠body） | 照常观测 | 照常，但 `lock_reference.lock_hash=UNKNOWN`，链条显式断开 | T5 |

优先级规则：wrapper 自己发出的 kill 观测 > 原始退出状态（防止把 TIMEOUT 误记
为 FAILED）——这是"能区分就区分，不能区分就 UNKNOWN"的延伸。

## 5. Phase 1 → Phase 2 provenance 链

- **链的锚点**：run record 不抄写 lock 文件里的 `lock_hash` 字符串，而是对
  lock body 重算 canonical hash 并与存储值**双向核对**——一致才引用。因此
  lock→run 是**可验证的密码学链接**，不是文件名拼接；篡改 lock 会被 run 当场
  降级为 UNKNOWN 引用（T5），改 run record 会破 `run_hash`（篡改测试）。
- Phase 1 遗留字段如期兑现：lock 的 `execution.start_time=UNKNOWN`（"run 未
  开始"）现在由 run record 的观测值补全；lock 的 `--command` 声明字段仍不反推
  （测试证明：lock 里 command=UNKNOWN，run 里 command=实际 argv——两扇门纪律
  在 Phase 2 同样成立）。
- artifacts 块呼应 v0.1 取证：GMMVI 的 `.csv/.csv.bad` membership 争议、
  TorchSSL 的 best−last 疑点在归档里靠文件名猜，现在每次运行的创建/修改文件
  连同 sha256 被逐条记录，成员身份成为可核对证据而非推断。
- **安全要求（Step 5）全部有测试**：① v1 全部源码 grep 不含
  password/passwd/secret/token/credential/api_key 任何凭据逻辑；② 环境变量蜜
  罐（`ED_CANARY_PASSWORD`）不出现在 bundle 任何文件中；③ run 前后项目外文件
  集合逐字节不变（无 `~/.config`/用户目录写入）；④ `.git/logs/HEAD` 字节不变
  + HEAD 不变（不改 git 历史）；⑤ 子进程正常继承环境（T7），工具自身不额外
  注入或读取任何凭据。

## 6. 仍未解决的 UNKNOWN（诚实清单）

1. **lock 内 `execution.start_time` 仍为 UNKNOWN**：按 Phase 1 设计 init 不填
   run 时刻；run record 已捕获真值，但"把 run 观测回填进 lock"属 verify 的
   declared-vs-observed 对账逻辑（Phase 3 禁令），本轮不做。
2. **budget（GMMVI sed 注入场景）**：任务书 Step 1 schema 无 budget 字段，
   Phase 2 未擅自扩块；`--timeout` 只捕获 wrapper 层的时限观测。
3. **metric 提取**：stdout 只作为原文证据保存，run record 没有 metric 字段
   （禁令：不得从 stdout 猜 metric）。
4. **删除的文件**：schema 只有 created/modified，删除记入 `artifacts.note` 文
   本而非结构化字段。
5. **Unix 信号退出码的 CLI 表达**：record 保真（如 -2），进程退出码降级为 1。
6. **timeout 后 kill 未确认生效**：整体退码取 1 且 exit_code=UNKNOWN，宁可
   UNKNOWN 不谎报已终止。
7. **Hydra/MLflow/W&B**：零集成（Phase 2 禁令），tracker 记录仍待 v1.1。

---

*Phase 2 交付终点。未 commit（Phase 3 起允许）；verify/audit 扩展未动。*
