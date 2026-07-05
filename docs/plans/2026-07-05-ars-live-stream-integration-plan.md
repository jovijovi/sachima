# Sachima 接入 agent-run-supervisor Live Stream 开发规划

> **For Hermes:** 这是 docs-only 规划文档。源码实现、真实 AGENT 执行、Gateway/Feishu 接入、生产配置写入、服务重启都需要后续单独明确批准。实现时使用 `subagent-driven-development` + TDD + Hermes 门禁 + Codex 只读 blocker review。

**日期：** 2026-07-05

**目标：** 让 Sachima 在安全、默认关闭、可回滚的边界内消费 `agent-run-supervisor` 的 live stream artifacts / cursor API，并把它呈现在 Sachima task workbench / 查询链路中。

**核心判断：** 当前已经有安全投影模块，但还没有真正接入工作台/查询面；下一步应先做本地/offline 的组合视图和 source binding，而不是部署或重启 Gateway。

---

## 1. 当前基线

### 1.1 agent-run-supervisor 已具备的能力

`agent-run-supervisor` 侧已经完成 live stream 基础能力与 caller-side read API：

- `progress.json`：结构化进度快照。
- `normalized-events.jsonl`：已归一化、已降敏的结构化事件流。
- `load_progress(artifact_dir)`：读取 `ProgressSnapshot | None`。
- `read_event_page(artifact_dir, after_seq=None, limit=100)`：按 cursor 分页读取 `EventPage(records, next_cursor, has_more)`。
- caller API 只暴露结构信号：`seq` / `family` / `kind` / `status` / `text_length` / 可选 summary；Sachima 侧当前策略是 **丢弃 summary**。

### 1.2 Sachima 已具备的能力

`release/sachima` 当前已经合并：

- Runtime spine core：`TaskRegistry` / `TaskEventLog` / deterministic projection / `LaunchSpec`。
- `AgentRunSupervisorPort`：本地/offline execution-port seam，支持 `create_or_attach` / `stream` / `signal` / `status` / `kill` / `liveness`。
- persistent lifecycle hardening：re-attach、cursor resume、snapshot、close/re-attach、status/liveness fail-closed。
- workbench view：`AgentRunSupervisorWorkbenchView`，可把 Status Projection + lifecycle snapshot 组合成平台中立工作台视图。
- production-shaped E2E：默认关闭、本地/offline、无真实 AGENT/Gateway/IM/Temporal Worker。
- live progress safe projection：`live_progress_projection.py`，已能把 ARS artifacts/cursor page 映射成 refs-only `LiveProgressProjection`。

当前 `release/sachima` head：`6b3dffd77`（PR #219 merge）。

### 1.3 当前缺口

现在距离“Sachima 接入 agent-run-supervisor live stream”还差三类工作：

1. **组合缺口：** `LiveProgressProjection` 还没有接入 `AgentRunSupervisorWorkbenchView` 或 task workbench 查询链路。
2. **绑定缺口：** Sachima 还没有 task/session → `artifact_dir` / `artifact_ref` 的 host-owned source binding。
3. **兼容性缺口：** 还没有用真实 `agent_run_supervisor.hermes_caller.events` 读取 synthetic artifact 的兼容性 smoke。
4. **运行态缺口：** 还没有 Gateway/Feishu/TUI 查询入口；所以当前不需要也不应该为了 PR #219 重启 Gateway。

---

## 2. Final target：接入完成的定义

“Sachima 接入 agent-run-supervisor live stream”在本阶段定义为：

```text
agent-run-supervisor live artifacts
  -> caller cursor/read API
  -> Sachima LiveProgressReader / source binding
  -> LiveProgressProjection
  -> AgentRunSupervisor live workbench/query view
  -> later Gateway/Feishu/TUI surface, still default-off until approved
```

完成后应满足：

- Sachima 可以按 `task_id` / `session_id` 查询一个受监督运行的 live progress。
- 查询结果只包含 refs / counts / closed state / cursor / stable error code。
- 支持 `after_seq = resume_cursor` 的增量读取，不重复显示事件。
- artifact 真实路径永远不出现在投影、日志、序列化输出或 IM-facing surface。
- ARS cursor 是 foreign read-model cursor，永远不写入 Sachima `TaskEventLog` seq。
- supervisor terminal state 只能作为 runtime observation，不能成为业务 verdict。
- 库缺失、artifact 缺失、corrupt、stale 都 fail closed。
- 默认关闭；没有真实 AGENT/Gateway/Feishu/Temporal Worker/production config 副作用。

---

## 3. 非目标 / 明确不批准

本规划不批准以下事项：

- 真实启动 Claude Code / Codex / acpx / npx / 外部 AGENT。
- Gateway route、Feishu/IM 发送、卡片更新、真实 delivery。
- Gateway reload/restart、systemd/service lifecycle。
- Temporal Worker/service/test server、Docker、daemon、socket listener。
- production config 写入、默认开启、public ingress/webhook。
- write-capable AGENT role。
- 把 raw `text` / `content` / `message` / `body` / stdout / stderr / prompt / tool output / ARS `summary` 暴露给 Sachima。
- 把 artifact filesystem path 暴露给 projection / workbench / status / IM。
- 把 ARS `seq` / cursor 写入 Sachima canonical `TaskEventLog`。

---

## 4. 开发分解

建议压缩为 **3 个实现 PR + 1 个后续 runtime canary/activation gate**。

### PR-LS1 — Live progress 接入 Task Workbench 组合视图

**目标：** 让 Sachima 的 agent-run-supervisor workbench 能组合展示现有 lifecycle/status view 与 live progress projection。

**建议文件：**

- Create: `sachima_supervisor/runtime_spine/agent_run_supervisor_live_workbench.py`
- Modify: `sachima_supervisor/runtime_spine/__init__.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_agent_run_supervisor_live_workbench.py`
- Optional docs/status cleanup: `docs/roadmap/current-status.md`

**建议 API：**

```python
def build_agent_run_supervisor_live_workbench_view(
    registry,
    port,
    ref,
    progress_reader,
    artifact_dir,
    artifact_ref,
    *,
    after_seq=None,
    limit=100,
    liveness=None,
):
    ...
```

**建议输出：**

```text
AgentRunSupervisorLiveWorkbenchView
  - type
  - task_id
  - session_id
  - workbench          # refs-only AgentRunSupervisorWorkbenchView dict
  - live_progress      # refs-only LiveProgressProjection dict
  - progress_available
  - progress_error_code
  - resume_cursor
  - has_more
  - stale
```

**TDD 验收：**

1. fake reader happy path：workbench + live progress 成功组合。
2. `after_seq` resume：第二页只包含 cursor 之后的 records。
3. missing progress：组合视图仍可构建，`progress_available=False`，stable error code。
4. corrupt event/page：fail closed，不泄漏异常文本或 raw field。
5. stale progress：`stale=True` 作为 observation，不阻塞 workbench。
6. task/session mismatch：fail closed，不拼错任务。
7. forged live projection/workbench view：validation fail closed。
8. serialized bytes 不含 `/home/`、`/tmp/`、`summary`、`text`、`content`、`message`、platform id canary。
9. import/build/serialize 不启动 Gateway/IM/Temporal Worker/subprocess/acpx/npx/socket。
10. `runtime_spine` adjacent suite 保持 green。

**边界：**

- `artifact_dir` 只传给 injected reader；组合视图只保留 `artifact_ref`。
- `LiveProgressProjection.resume_cursor` 只用于下一次 ARS artifact read，不进入 `TaskEventLog`。
- 这一步仍然不读取真实 live run，不接 Gateway。

**完成定义：**

- 新组合视图可由 fake reader 构建、验证、序列化。
- 所有 no-leak / forbidden-surface gates 通过。
- Codex 只读 blocker review 通过。
- PR 合并后，Sachima 已有一个可查询的本地/offline live workbench composition surface。

### PR-LS2 — Live progress source binding / cursor state

**目标：** 让 Sachima 有一个 host-owned 私有绑定层，知道某个 `task_id` / `session_id` 对应哪个 ARS artifact source。

**建议文件：**

- Create: `sachima_supervisor/runtime_spine/live_progress_sources.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_live_progress_sources.py`
- Optional integrate with PR-LS1 builder tests。

**建议模型：**

```text
LiveProgressSource
  - task_id
  - session_id
  - artifact_ref       # safe public id
  - artifact_dir       # private local path, never projected
  - last_seen_cursor   # optional, foreign ARS cursor only
```

**建议 API：**

```python
register_live_progress_source(task_id, session_id, artifact_dir, artifact_ref)
resolve_live_progress_source(task_id, session_id) -> LiveProgressSource | unavailable
update_live_progress_cursor(task_id, session_id, cursor)
build_bound_live_progress_view(...)
```

**TDD 验收：**

1. register + resolve happy path。
2. source missing → stable unavailable，不 crash，不 fake success。
3. unsafe `artifact_ref` / task/session id fail closed。
4. path-looking `artifact_ref` fail closed。
5. `artifact_dir` 可以是内部私有值，但永远不出现在 `as_dict()` / serialized bytes。
6. cursor resume no duplicate；bool-as-int、negative、oversized cursor fail closed。
7. forged source object validation fail closed。
8. no platform id / raw path / raw exception leak。

**边界：**

- source binding 是 host-owned local state，不是业务 verdict。
- 不把 binding 写进 Event Log raw event body。
- 不做无限 polling loop；只做 bounded query/read helper。

**完成定义：**

- Sachima 能从 task/session 找到安全 artifact source，并用它构建 PR-LS1 组合视图。
- artifact path 仍然是内部实现细节。

### PR-LS3 — 真实 ARS caller API 兼容性 smoke

**目标：** 在不启动真实 AGENT 的前提下，用真实 `agent_run_supervisor.hermes_caller.events` 读取 synthetic artifact，证明 Sachima reader contract 与 ARS caller API 对齐。

**建议文件：**

- Create: `sachima_supervisor/runtime_spine/agent_run_supervisor_live_progress_smoke.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_agent_run_supervisor_live_progress_smoke.py`

**建议行为：**

- 若 `agent_run_supervisor` 可 import：读取 synthetic `progress.json` + `normalized-events.jsonl`，构建 Sachima projection / live workbench view。
- 若不可 import：返回 stable blocked/unavailable report；不把 import error 原文暴露。
- smoke 只读 fixture，不跑 acpx/npx，不启动 agent，不写 production config。

**TDD 验收：**

1. synthetic artifact + real caller API → projection available。
2. `has_more` / `next_cursor` / `after_seq` 行为对齐。
3. nullable `kind` / `status` / `text_length` 行为对齐。
4. legacy no-`seq` fallback 行为对齐。
5. corrupt `progress.json` / corrupt event → stable fail-closed。
6. import absent → unavailable/blocked report，不 crash。
7. no-leak bytes scan。
8. no hard dependency unless后续单独批准 pin/provision policy。

**完成定义：**

- Sachima 与真实 ARS caller API 的字段、cursor、nullable 行为被测试锁住。
- 后续接 runtime 时不会靠猜字段名。

### PR-LS4 — 默认关闭的查询入口 / Runtime Activation Gate（后续单独批准）

**目标：** 在 PR-LS1–LS3 green 之后，再决定是否把查询入口接到 Gateway/Feishu/TUI。

**候选能力：**

```python
query_task_live_progress(task_id, session_id, after_seq=None, limit=100)
```

**可能 surface：**

- Hermes internal query helper。
- Gateway API / IM task workbench。
- TUI task workbench。
- Feishu task card refresh。

**这一步才可能需要：**

- Gateway 代码改动。
- Gateway restart/reload。
- Feishu/card/rendering 设计。
- runtime smoke / single-channel canary。

**前置条件：**

- PR-LS1–LS3 合并。
- 明确 query surface、用户/channel/task scope。
- 明确是否允许 Gateway restart。
- 明确是否允许任何真实 IM update/send。
- 具备 rollback / kill switch / no-double-send / no-leak gate。

---

## 5. 推荐立即开工项

推荐下一步只批准 **PR-LS1**：

```text
批准执行 PR-LS1：Sachima 接入 agent-run-supervisor live progress 到 task workbench 组合视图。
范围限于本地/offline source/tests/docs；允许新增 agent_run_supervisor_live_workbench.py 和对应测试，修正 current-status 过期 wording；不允许 Gateway/Feishu/live/default-on、真实 AGENT/acpx/npx 执行、Temporal Worker/service、production config、真实 delivery。按 TDD、Hermes gates、Codex 只读 review、PR/CI/审批卡流程执行。
```

为什么先做 PR-LS1：

- 它是最小 behavior-bearing step。
- 它复用已合并的 PR #219 投影模块，不重复造轮子。
- 它不碰真实 runtime/Gateway，风险最低。
- 它让“接入 live stream”第一次出现在 Sachima 可查询产品 surface，而不是只停留在独立 projection 模块。

---

## 6. 通用验证门禁

每个实现 PR 至少运行：

```bash
uv run --frozen --extra dev python -m pytest tests/sachima_supervisor/runtime_spine/<focused_test>.py -q
uv run --frozen --extra dev python -m pytest tests/sachima_supervisor/runtime_spine -q
uv run --frozen --extra dev --extra flowweaver-temporal python -m pytest tests/sachima_supervisor -q
uv run --frozen --extra dev python -m ruff check <changed_python_files>
python -m compileall <changed_python_files>
git diff --check
```

并执行 added-lines / changed-files forbidden-surface scan，至少覆盖：

```text
subprocess
os.system
.popen(
acpx
npx
socket.socket
Client.connect
Worker
WorkflowEnvironment
Gateway
Feishu
IM send
delivery
public ingress
webhook
production config
```

no-leak scan 至少覆盖：

```text
/home/
/tmp/
/var/
/users/
text
content
message
body
summary
stdout
stderr
prompt
tool output
chat_id
open_id
token
secret
signed
```

---

## 7. Review / merge 流程

每个实现 PR 应走：

1. Claude Code Architect / design teach-back（只问 blocker，不让它扩 scope）。
2. Claude Code Main Programmer TDD 实现。
3. Hermes 运行门禁与 no-leak / forbidden-surface scans。
4. Codex CLI repo-aware read-only blocker review。
5. 修复 blocker 后重跑门禁和 blocker-only re-review。
6. open PR，发送 head-SHA-bound Feishu merge approval card。
7. merge 前 fresh head check + required gates。

---

## 8. 状态汇报规则

后续汇报必须区分：

- 规划文档已保存。
- 源码实现是否开始。
- 测试是否通过。
- PR 是否打开/合并。
- runtime checkout 是否部署/重启。
- Gateway/Feishu 是否启用。
- 真实 AGENT/live stream 是否已经跑过。

在 PR-LS4 之前，不得声称“已上线 live progress”或“Gateway 已接入”。准确说法应是：

```text
Sachima 已具备/正在具备 agent-run-supervisor live stream 的安全本地查询链路；生产/Gateway/Feishu 启用仍需后续单独批准。
```
