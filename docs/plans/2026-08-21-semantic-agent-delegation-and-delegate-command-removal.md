# Sachima 语义 AGENT 委派与 `/delegate` 移除实施计划（仅文档候选 / 实施未授权）

> 状态：**docs-only candidate / implementation not authorized**
> 目标路径：`docs/plans/2026-08-21-semantic-agent-delegation-and-delegate-command-removal.md`
> 本计划不授权源码、测试或配置变更，不授权提交、推送、PR、合并、服务调用、真实 AGENT 执行、重启或部署。

## 目标

将外部 AGENT 委派的唯一用户入口改为 Hermes 自然语言交互：Hermes 识别意图、澄清并选择 canonical `agent_id`；Sachima 仅做 live roster 与 execution preset 的确定性校验，并复用现有 `sachima_delegate_control`、协调器及完整持久化运行闭环。

删除用户可见 `/delegate`。删除后，旧 `/delegate ...` 输入不获得兼容垫片、弃用提示、迁移提示、特殊拦截或任何定制行为，只按普通系统输入/未知命令路径处理。

## 非目标

- 不在 Sachima 内实现 ARS roster 服务，也不读取 `agents.toml` 代替 daemon 实时事实。
- 不在 Gateway/Sachima 新建角色路由器、模糊匹配、别名表或 Feishu 身份到 AGENT 的映射。
- 不改动通用 `tools/delegate_tool.py`、Hermes `delegate_task` 或其他 subagent 能力。
- 不删除服务于通用平台行为的 Feishu mention 规范化、重叠与来源安全逻辑。
- 不重写 task/Run/Session 恢复、取消、结果投递、幂等、容量或 uncertain-submit 语义。
- 不启用真实 ARS、IM、provider、生产配置或默认开启路径。

## 修正后的架构与所有权

```text
用户自然语言
  │
  ▼
Hermes Session
  ├─ 语义意图、显式名字理解、角色/功能选择
  ├─ 候选不唯一时澄清
  └─ “Tom 不是 AGENT”等纠正仅留在当前 Session 对话状态
  │ canonical agent_id
  ▼
sachima_delegate_control（唯一内部控制面）
  │
  ├─ ARS 只读 live roster ───────┐
  └─ Sachima execution presets ──┴─ 精确交集校验
  │
  ▼
既有 SachimaDelegateCoordinator
  ▼
既有 task / Run / Session 持久化、恢复、控制、回执、结果与下一轮上下文
  ▼
ARS 执行与证据；Gateway 仅负责宿主绑定、会话交互和投递
```

ARS 拥有注册 roster 与执行事实；Sachima 拥有 preset、task binding 和确定性执行校验；Hermes 是唯一语义路由与对话权威。

## 当前基线

- 基线为 `release/sachima @ 320c4b31ab465054324d435257e0faa88459f01a`。
- delegate 专项基线为 186 个通过测试，覆盖 state、coordinator、result、command、selection。
- ARS 0.7.7 的 `server_info` 不提供 roster，daemon 启动后不热加载 `agents.toml`；因此 live roster 是外部阻断依赖。
- 当前路线图未授权本功能的源码实施、Gateway/Feishu/live/default-on、真实执行、生产配置或服务生命周期。本次仅产出候选计划。

## 保留 / 移除矩阵

| 范围 | 决策 | 实施约束 |
|---|---|---|
| `gateway/sachima_delegate_state.py` | 保留 | task、turn、result 与既有字段/版本保持可读，不做数据迁移 |
| `gateway/sachima_delegate.py` | 保留并瘦身 | 保留容量、幂等、恢复、create/status/cancel/continue/recover/result；删除命令专用文案和路由职责 |
| `gateway/sachima_delegate_result.py` | 保留 | 回执、终态单次投递、Hermes 下一轮结果上下文及双 sink settlement 不变 |
| `gateway/run.py` | 局部移除 | 保留启动 restoration、delivery factory、result-context consume/settle；仅删 `/delegate` active/cold bypass |
| `gateway/slash_commands.py` | 局部移除 | 删除 `_handle_delegate_command`；保留语义路径所需的 delivery 构造 |
| `hermes_cli/commands.py` 的 gateway-only `CommandDef` 及派生 help/catalog/menu | 移除 | 删除共享 registry 中的命令定义，使 Gateway help、Telegram、Slack 等派生面同步消失 |
| `gateway/sachima_delegate_selector.py` | 删除 | 无用户命令 selector、无 mention→AGENT 解析 |
| `gateway/sachima_delegate_policy.py` | 替换/重塑 | 仅保留 execution preset 校验；移除 mentions、`auto_selectable`、priority、capability 路由和 `resolve_route` |
| `tools/sachima_delegate_control_tool.py` | 修改 | create/continue 的创建或换 AGENT 路径接收 Hermes 选择的 canonical `agent_id`，不再接收 `requested_profile_id` |
| 通用 Feishu mention 与 `tools/delegate_tool.py` | 明确保留 | 不因本功能移除而删除或重构 |

内部已有 `delegate` 命名、稳定错误码或持久化 envelope 不因文案清理而机械改名；只有确属 `/delegate` 用户命令的表面被移除。

## 实施阶段

### 阶段 1：锁定 ARS live roster 依赖

依赖外部 ARS 先交付并发布版本化、只读、可契约测试的 live roster API。发布后再按官方协议更新精确依赖与现有 Socket facade/contract；不猜测操作名或响应结构，不提供共享文件回退。

可能涉及：

- `sachima_supervisor/runtime_spine/arsd_socket_contract.py`
- `sachima_supervisor/runtime_spine/arsd_supervisor_backend.py`
- `sachima_supervisor/runtime_spine/agent_run_supervisor_execution_binding.py`
- 对应 `tests/sachima_supervisor/runtime_spine/test_arsd_*.py`

退出条件：注入式契约测试能区分 registered、absent 与协议不可用；版本/pin 一致；未进行真实 socket 调用。**任何依赖 live roster 的 Sachima 实现，在该 API 独立交付、版本锁定并通过契约测试前不得宣称完成。**

### 阶段 2：建立语义控制与 execution preset 校验

以 TDD 将旧 routing policy 重塑为 execution preset catalog；建议新模块为 `gateway/sachima_agent_execution_presets.py`，替代旧 policy 模块。Preset 只绑定 canonical `agent_id` 与已批准的 workspace、model、effort、permissions/agent-policy、limits，不承载语义排名、mention 或平台身份。

修改：

- `tools/sachima_delegate_control_tool.py`
- `gateway/sachima_delegate.py`
- `gateway/sachima_live_progress_binding.py`
- execution preset 模块及其新测试

规则：

- create 与需要判断/切换 AGENT 的 continue 使用 exact canonical `agent_id`。
- 执行资格为 `live roster ∩ valid execution preset`；任一侧缺失都不提交 Run。
- 新注册但无 preset 的 AGENT 可报告为 registered，但执行状态为 unavailable，绝不继承 Claude/default 配置。
- 功能候选不唯一时由 Hermes 澄清，控制面不得以 priority 或模糊匹配代选。
- 同 AGENT continuation 与换 AGENT 后建立 linked task 的既有语义保持不变。
- “Tom 不是 AGENT”的纠正只依赖当前 Hermes Session 对话状态，不写全局 alias、memory 或配置。
- 不新增 core tool；只使用现有 `sachima_delegate_control`/coordinator 控制面。

### 阶段 3：原子移除 `/delegate` 及重复路由

仅在阶段 2 的自然语言创建路径和回归测试成立后，原子移除命令入口，避免出现“旧入口已删、新入口不可用”的中间版本。

执行 transitive-removal inventory：

- command registry、Gateway help/catalog、Telegram/Slack 菜单与权限清单；
- `_handle_delegate_command`；
- busy-agent fast path 与 cold path；
- selector 模块及其消费者；
- mention→AGENT mapping；
- `resolve_route`、自动候选、priority、`requested_profile_id`；
- 旧命令文案、专用常量、陈旧文档与测试。

重点文件：

- `hermes_cli/commands.py`
- `gateway/slash_commands.py`
- `gateway/run.py`
- `gateway/sachima_delegate_selector.py`（删除）
- `gateway/sachima_delegate_policy.py`（删除或由 preset 模块替代）
- `tests/gateway/test_sachima_delegate_command.py`
- `tests/gateway/test_sachima_delegate_selection.py`
- `tests/gateway/test_command_bypass_active_session.py`

逐项审查 `tests/gateway/test_feishu.py` 中的命中：只移除委派专属断言；通用 mention 规范化、重叠与 bot mention 安全测试必须保留。明确排除 `tools/delegate_tool.py` 及其测试。

### 阶段 4：回归闭环与文档对账

将命令测试拆为语义控制/执行 preset 测试；保留并继续运行 coordinator、state、result、restoration、delivery 和 result-context 测试。实现完成后检查维护中的用户文档/help；历史日期计划保留为历史证据，不反向改写。

仅当实际源码真相改变路线图状态时，才在后续实施中更新 `docs/roadmap/current-status.md`；仅当产品目标确实改变时更新 `GOAL.md`。同时检查 `docs/sachima-channel.md`、网站/help/catalog 等维护面。本 docs-only 任务不修改它们。

## TDD 与验收场景

先写失败测试，再完成最小实现：

1. Fixture roster 与 preset 均含 canonical `codex`：“让 Codex 检查这个方案”由 Hermes 解析并归一到内部 `agent_id=codex`，调用同一内部工具，且仅产生一次 durable task/submit/回执。
2. “找一个适合做架构设计的 AGENT”：唯一合格候选才创建；零个或多个候选时 Hermes 澄清，Sachima 不写 task、不提交。
3. “让 Tom 查天气”：live roster 无 exact `Tom` 时不做模糊匹配并澄清；用户说明 Tom 不是 AGENT 后，仅当前 Session 抑制该解释。
4. Roster 有 AGENT、preset 缺失：显示 registered/unavailable，不继承默认 Claude 配置，不提交。
5. Preset 存在、roster 缺失：拒绝执行，不读取 `agents.toml`。
6. status/cancel/continue/recover/result、capacity、idempotency、uncertain-submit、启动恢复、回执、终态投递和下一轮上下文保持原行为。
7. 既有 durable fixture 可由新代码读取；旧任务仍可查询、取消、恢复、取结果。新的 continuation 仍须满足当前 live roster 与 preset。

`/delegate` 的移除通过 registry、handler、selector、专用分支和文案的缺失性检查证明；不新增针对旧 `/delegate ...` 输入的兼容、弃用、迁移或特殊行为测试。

单元测试只使用注入 facade、fake roster、临时状态和脚本化 provider/tool-call；不得连接真实 ARS/IM/provider，不得声称 live E2E。真实多 AGENT 验证留待独立批准。

## 验证

聚焦测试至少覆盖：

- 新增 semantic-control、roster-contract、execution-preset 测试；
- `test_sachima_delegate_coordinator.py`
- `test_sachima_delegate_state.py`
- `test_sachima_delegate_result.py`
- `test_sachima_live_progress_library_binding.py`
- `test_command_bypass_active_session.py`
- `test_provider_dispatch_signal.py`
- 平台 result/format 与通用 Feishu mention 测试。

随后运行相关 Gateway、tools、runtime-spine 较宽测试及仓库标准测试入口。静态检查包括：

```bash
ruff check <changed-files-and-tests>
python -m compileall gateway tools sachima_supervisor/runtime_spine
git diff --check
git status --short
```

再以源码搜索审计活动源码、命令目录、help/catalog、测试和维护文档中的 `/delegate`、`resolve_route`、`requested_profile_id`、mention mapping 与自动路由残留；允许历史计划及仍有意义的内部 durable `delegate` 命名，不做盲目全局改名。

## 兼容与回滚

- `/delegate` 无运行时兼容路径；源码回滚若需恢复旧命令，只能回退本次精确实施变更。
- 旧 routing policy 不再是路由权威，也不静默降级或合成默认 preset；生产 preset 配置迁移属于独立审批。
- coordinator/state schema 保持不变，既有 durable records 无需迁移且持续可读。
- 若新路径回滚，恢复命令代码与相关源码即可；不得保留永久双入口。任何已单独启用的运行时配置须在其独立审批下回退。

## 审批矩阵

| 边界 | 当前状态 | 单独批准后才允许 |
|---|---|---|
| 本计划验收 | 本次可审阅 | 仅确认计划内容 |
| Sachima 源码与测试实施 | 未授权 | 阶段 1–4 的本地代码、测试与实施期文档变更 |
| 外部 ARS roster prerequisite | 未交付/未授权 | ARS API 设计、发布、版本 pin 与契约接入 |
| commit / push / PR / merge | 未授权 | 任一仓库历史或远端变更 |
| 运行时配置与功能激活 | 未授权 | preset 配置、toolset/surface 开启或生产写入 |
| Gateway restart / deploy | 未授权 | 重启、重载、部署或生产流量接入 |
| live multi-agent canary | 未授权 | 真实 ARS、IM、provider 或 AGENT 执行与证据采集 |
