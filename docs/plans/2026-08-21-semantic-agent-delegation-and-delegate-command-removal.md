# Sachima 语义 AGENT 委派与 `/delegate` 移除实施计划（已受理并实施）

> 状态：**accepted plan / stages 1–4 implemented locally**
> 目标路径：`docs/plans/2026-08-21-semantic-agent-delegation-and-delegate-command-removal.md`
> 本计划的源码与测试实施已完成，范围限于本仓库工作区。仍未授权：提交、推送、PR、合并、生产配置写入、
> preset 运行时启用、Gateway/服务重启、部署，以及任何真实 ARS / IM / provider / AGENT 调用。

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
  ├─ Sachima execution presets ──┼─ 精确交集校验
  └─ Sachima role/division 目录 ─┘  （仅 agents 只读发现动作使用）
  │
  ▼
既有 SachimaDelegateCoordinator
  ▼
既有 task / Run / Session 持久化、恢复、控制、回执、结果与下一轮上下文
  ▼
ARS 执行与证据；Gateway 仅负责宿主绑定、会话交互和投递
```

ARS 拥有注册 roster 与执行事实；Sachima 拥有 preset、task binding 和确定性执行校验；Hermes 是唯一语义路由与对话权威。

## 基线与已消费的外部事实

- 实施基线为 `release/sachima @ 9c7366774f`（分支 `feat/semantic-agent-delegation`，起始 HEAD `156d9c6573`）。
- delegate 专项实施前基线为 253 个通过测试，覆盖 state、coordinator、result、command、selection，以及
  command-bypass 与 provider-dispatch-signal。
- **外部阻断依赖已解除**：`agent-run-supervisor 0.7.8` 已发布并部署，Socket API v3 新增只读
  `agent_list`，官方 client 返回 `{"agent_ids": [<canonical agent id>]}`，生产实测 roster 为
  `claude`、`codex`、`cursor`、`oh-my-pi`、`opencode`。0.7.7 → 0.7.8 的包内差异仅为该操作本身
  （`protocol.OPERATIONS`、`client.agent_list`、handler 与版本号），wire、limits、错误码与 Session/Run
  语义均未变，因此 API version 仍为 3。
- 运行时启用（preset 配置写入、toolset 开启、Gateway 重启、真实 daemon 访问）仍未授权，本次实施不触及。

## 保留 / 移除矩阵

| 范围 | 决策 | 实施约束 |
|---|---|---|
| `gateway/sachima_delegate_state.py` | 保留 | task、turn、result 与既有字段/版本保持可读，不做数据迁移 |
| `gateway/sachima_delegate.py` | 保留并瘦身 | 保留容量、幂等、恢复、create/status/cancel/continue/recover/result；删除命令专用文案和路由职责 |
| `gateway/sachima_delegate_result.py` | 保留 | 回执、终态单次投递、Hermes 下一轮结果上下文及双 sink settlement 不变 |
| `gateway/run.py` | 局部移除 | 保留启动 restoration、delivery factory、result-context consume/settle；仅删 `/delegate` active/cold bypass |
| `gateway/slash_commands.py` | 局部移除 | 删除 `_handle_delegate_command`；保留语义路径所需的 delivery 构造 |
| `hermes_cli/commands.py` 的 gateway-only `CommandDef` 及派生 help/catalog/menu | 移除 | 删除共享 registry 中的命令定义，使 Gateway help、Telegram、Slack 等派生面同步消失 |
| `gateway/sachima_delegate_selector.py` | 已删除 | 无用户命令 selector、无 mention→AGENT 解析 |
| `gateway/sachima_delegate_policy.py` | 已删除，由 `gateway/sachima_agent_execution_presets.py` 取代 | 仅保留 execution preset 校验；mentions、`auto_selectable`、priority、capability 路由与 `resolve_route` 均已移除 |
| `tools/sachima_delegate_control_tool.py` | 已修改 | create/continue 接收 Hermes 选择的 canonical `agent_id`，`requested_profile_id` 已移除 |
| 通用 Feishu mention 与 `tools/delegate_tool.py` | 明确保留 | 不因本功能移除而删除或重构 |

内部已有 `delegate` 命名、稳定错误码或持久化 envelope 不因文案清理而机械改名；只有确属 `/delegate` 用户命令的表面被移除。

## 实施阶段

阶段 0 是阶段 1–4 的前置条件。它在本次实施中以 preset 权限契约的形式闭环（见该阶段末的实施结论）；真实授权验证仍是独立批准项。

### 阶段 0：开发型 AGENT 基础权限闭环（阶段 1 前置条件）

先证明“被委派的开发型 AGENT 真的能干活”。权限不闭环时，后续 `live roster ∩ preset` 校验只会把不可用的执行路径包装得更精致。

工程基线（engineering baseline）：

- 基础授权面为 **read + search + execute**：读取工作区文件、检索代码、执行常规开发命令（构建、测试、静态检查、只读 git 查询）属于基线能力，不按逐次例外处理。
- **实施型 preset 在基线之上追加 write**（编辑与新建工作区文件）。
- **delete / move 与特权副作用**（越出工作区的路径、网络投递、凭据访问、服务生命周期）不进入基线，按 task 单独定义与批准。
- **`execute` 是协作型能力（cooperative capability），不是 OS 级隔离**：shell 命令在 execute 之下仍可写入、删除、移动文件，发起网络请求，读取凭据或操作服务生命周期。因此“不单列 write / delete / move 等能力标签”只表示未授予对应语义授权，不构成 OS 级阻止。收敛由 **task 契约 + 前后副作用 guard** 落实——它们检测并强制被限定的契约；面向敌意行为的强阻止需独立 UID、容器、VM、只读挂载或等效隔离。特权副作用无论如何仍须单独批准。

只读评审（read-only review）的定义：

- 只读指**不留下持久变更**（no retained mutation），由 task 前后的工作区 guard 比对证明；
- **不等于禁止执行命令**：评审型路由仍可运行测试、构建与检索命令；临时产物须在 task 内清理或落在被忽略的临时目录，post-guard 必须与 pre-guard 相等。

ARS 与调用方的职责边界：

- 仅当出现**可复现的映射/中介缺陷**（调用方已发出的授权在 ARS 侧被错误翻译、丢失或过度收窄）时，才要求改动 ARS core；此类改动需独立证据与独立批准。
- 其余情况由**调用方与 preset 拥有 grant 本身**：授权内容、粒度与密封形式由 preset 定义；**能力集合变化即须重新生成其身份**（preset/grant identity 及其 sealed 摘要），不得在旧身份下静默扩权或静默收窄。

退出条件：

- 已注册的工程型路由能完成真实的 read / search / benign execute；
- **每条配置为实施型（write-capable）的路由，还须在 read + search + execute + write 之下完成一次真实的 benign 写入/新建**：事前声明精确的期望工作区 delta，实测 delta 与之逐项相等，全程无 permission violation，并留下清理/回滚证据（task 结束后工作区回到基线）。**评审型（只读）路由不要求该写入证明。**
- 生效授权（effective grant）与 preset 声明的 sealed grant 精确一致，无隐式加宽、无静默降级；
- 全程无 permission violation；
- 子进程被正确回收（process reap），无残留进程或孤儿句柄；
- 评审型 task 结束后工作区与基线一致（pre/post guard 相等）。

**实施结论：** 本阶段在本次实施中落到 preset 契约层——`permissions` 是一个受控词表
（`read`/`search`/`execute`/`write`）上的显式声明，必须至少包含工程基线 `read + search + execute`，
`write` 表示实施型 preset，且必须是 ARS 配置 `grant_capabilities` 的子集（只能收窄，不能加宽）。
它是**声明**而非 OS 级隔离：真实收敛仍由 task 契约与前后副作用 guard 承担。本次未执行真实授权验证、
未写入生产配置、未开启任何 preset。

### 阶段 1：锁定 ARS live roster 依赖

依赖外部 ARS 先交付并发布版本化、只读、可契约测试的 live roster API。发布后再按官方协议更新精确依赖与现有 Socket facade/contract；不猜测操作名或响应结构，不提供共享文件回退。

可能涉及：

- `sachima_supervisor/runtime_spine/arsd_socket_contract.py`
- `sachima_supervisor/runtime_spine/arsd_supervisor_backend.py`
- `sachima_supervisor/runtime_spine/agent_run_supervisor_execution_binding.py`
- 对应 `tests/sachima_supervisor/runtime_spine/test_arsd_*.py`

退出条件：注入式契约测试能区分 registered、absent 与协议不可用；版本/pin 一致；未进行真实 socket 调用。**任何依赖 live roster 的 Sachima 实现，在该 API 独立交付、版本锁定并通过契约测试前不得宣称完成。**

**实施结论（已完成）：**

- pin/lock/anchor 从 0.7.7 推进到 0.7.8：`pyproject.toml` 的 `agent-run-supervisor` extra 与其 `dev`
  镜像、`EXPECTED_AGENT_RUN_SUPERVISOR_VERSION`、重新生成的 `uv.lock`，以及仅针对该包收窄的
  `[tool.uv].exclude-newer-package` 截止时间（全局 7 天供应链窗口不变）。
- `ARSD_OPERATIONS` 成为闭合八操作集，并对 `protocol.OPERATIONS` 做 drift-lock；缺少 `agent_list` 的
  daemon 在 `server_info` 协商阶段即被拒绝，没有降级路径。
- 新增 `validate_arsd_agent_list`：顶层键集恰为 `{"agent_ids"}`、值为 list、每个 id 精确匹配镜像自
  `native_acp.agent_registration.AGENT_ID_RE` 的 canonical 文法、严格升序（因而唯一）、页面有界
  (`ARSD_MAX_REGISTERED_AGENTS`)。任何偏差都是单一稳定码 `runtime_arsd_protocol_violation`，且不回显输入。
  升序与唯一性按官方契约断言：daemon 的 `_agent_list` 直接返回 `tuple(sorted(entries))`。
- facade（Protocol 与 `DefaultArsdClientFacade`）新增 `agent_list`；`ArsdSupervisorBackend.list_registered_agents()`
  每次现读、不缓存，传输失败为 `runtime_arsd_unavailable` 而非空 roster，`UNKNOWN_OP` 走既有映射。
- 产品测试只用注入 fake，无真实 socket 调用。

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
- preset 的 permissions/agent-policy 直接采用阶段 0 基线：工程型 preset 至少含 read + search + execute，实施型再加 write；delete/move 与特权副作用不由 preset 默认授予，须 task 级定义并单独批准。preset 未列出的能力标签只表示未授予语义授权，其实际收敛依赖 task 契约与 pre/post 副作用 guard，不得当作 OS 级阻止。
- 评审型 preset 以“无持久变更 + pre/post guard”表达只读，不以“禁止执行命令”表达。
- preset 能力集合变化视为新身份：重新生成并密封 grant identity，旧 identity 不得继续复用；ARS core 改动只在证实映射/中介缺陷时提出。
- 功能候选不唯一时由 Hermes 澄清，控制面不得以 priority 或模糊匹配代选。
- 同 AGENT continuation 与换 AGENT 后建立 linked task 的既有语义保持不变。
- “Tom 不是 AGENT”的纠正只依赖当前 Hermes Session 对话状态，不写全局 alias、memory 或配置。
- 不新增 core tool；只使用现有 `sachima_delegate_control`/coordinator 控制面。

**实施结论（已完成）：**

- 新模块 `gateway/sachima_agent_execution_presets.py` 取代并删除了 `gateway/sachima_delegate_policy.py`。
  preset 只持有 canonical `agent_id`、五类 ref、`permissions` 与 `max_task_bytes`；文档键集是封闭的，
  写入 `profile_id`/`mentions`/`auto_selectable`/`priority`/`capabilities` 等任一旧字段都会 fail closed。
- 追加校验：preset 的 `agent_id` 必须与 `config.agent_by_policy_ref[agent_policy_ref]` 精确相等，
  否则会出现"命名一个 AGENT、实际运行另一个"的静默错配。
- 无 preset 文件时使用**空目录**（`empty_agent_execution_presets()`），不再合成 legacy 单 profile；
  环境变量相应改为 `SACHIMA_AGENT_EXECUTION_PRESETS_FILE`。
- `admit_agent_execution` 是纯函数：文法 → 注册 → preset → 任务体积，四种拒绝各有稳定码
  (`sachima_agent_invalid_id` / `..._not_registered` / `..._no_preset` / `..._task_too_large`)，
  另有 `..._roster_unavailable` 表示"问不到"而非"没有"。查找完全精确，无 case folding、无 trim、无近似。
- `SachimaDelegateCoordinator.admit_agent()` 组合"live roster 读 + preset 交集"，同步、无副作用；
  `create()` / `continue_task()` 改收 `preset`，`bind_delegate_coordinator(..., presets=...)`。
- `tools/sachima_delegate_control_tool.py` 的参数由 `requested_profile_id` 改为 `agent_id`：create 必填；
  continue 省略即沿用本 task 的 AGENT、相同即同 task 续跑、不同即建立 linked task。**任何会提交 Run 的
  continuation 都重新做一次资格校验**，因此已下线的 AGENT 不会继续收到新 Run。拒绝时返回
  `{refusal, agent_id, registered}`——`registered` 让 Hermes 能区分"注册了但本机不可执行"与"没有这个 AGENT"，
  `agent_id` 只在通过文法后回显。
- 持久层字段 `profile_id` 更名为 `agent_id` 并改用 canonical 文法（旧 `_safe_ref` 容不下 `oh-my-pi` 的连字符）；
  `from_dict` 兼容读取旧键，旧记录无需迁移，仍可查询/取消/恢复/取结果。
- `tools/delegate_tool.py` 未改动，未新增 core tool。

**独立评审后的三处修复（同一实施内完成）：**

1. **grant 按 policy 密封**（原缺陷：preset 声明 `read/search/execute`，但 `build_arsd_submit_payload`
   始终发送 config 全局 `grant_capabilities`，评审型 Run 仍拿到 `write`）。新增可选配置映射
   `grant_by_policy_ref`，为每个 `agent_policy_ref` 给出其 Run 的**确切**能力集；preset 声明的
   `permissions` 必须与之逐项相等，否则不构建。身份由 `derive_arsd_sealed_grant` 从
   （操作者 `grant_ref`/`grant_hash`/`grant_role_hash` + 确切能力集）确定性派生：与全局集合相同则
   原样沿用操作者身份，任何**收窄**都得到自己的 `grant_ref`/`grant_hash`/`grant_role_hash`，
   **加宽**直接 fail closed。派生是确定性的，因此 recovery 仍重发字节一致的 payload；能力集来自
   config 闭合映射而非调用方参数，"每个 policy-facing 值都经 config 解析"的信任不变。未改 ARS core。
2. **选择输入大小写不敏感的精确匹配**。preset/config 的 id 仍是严格 canonical 小写；用户/Hermes 的
   选择输入经 `resolve_selected_agent_id` 对 live roster 做 casefold 精确匹配，只宽容大小写——不 trim、
   不模糊、不别名、不子串；casefold 冲突 fail closed。返回、准入与持久化的一律是 roster 的 canonical 拼写。
3. **角色/分工路由闭环**，见下节。

### 阶段 2b：角色/分工目录与只读发现动作

“找一个适合做架构设计的 AGENT”需要三个 Hermes 看不到的确定性事实：谁当前注册、本机可运行谁、谁持有
哪个角色。原实施只暴露了前两个的交集且只接受已选定的 `agent_id`，因此该场景无法作为产品路径执行。

修复保持所有权分线，不把语义放进 execution preset：

- 新模块 `gateway/sachima_agent_role_policy.py` 只承载 `agent_id` → division + roles。文档键集封闭，
  写入 `priority`/`weight`/`rank`/`aliases`/`mentions`/`platform`/`default` 任一都 fail closed；
  没有任何排序字段。
- `build_agent_eligibility_view` 以 live roster 为总体做左连接：每个已注册 AGENT 都出现，
  `registered` / `executable` / `division` / `roles` / `role_routable` 分开报告。缺 preset 或缺角色者
  可见为 registered 但不可自动路由，且绝不继承他人配置；roster 之外的配置项不出现。
- `select_agent_by_role` 做精确交集：恰好一个合格候选可选；零个与多个各有稳定码
  （`sachima_agent_role_no_candidate` / `sachima_agent_role_ambiguous`）并附候选列表供 Hermes 澄清。
  **没有任何 tie-break**——不按 priority、不按字母序、不按上次结果。
- 控制面新增**只读** `agents` 动作（可选 `role` / `division` 过滤），不写 task、不建 Session、不提交 Run，
  因此“零个或多个”这一答案本身不产生任何持久状态。发现之后仍以 exact `agent_id` 调用 `create`，
  显式选择因而始终可审计。
- 目录文件由 `SACHIMA_AGENT_ROLE_POLICY_FILE` 提供；缺省为空目录：所有 AGENT 仍可按名调用，
  没有任何 AGENT 可按角色被选中。

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

**实施结论（已完成）：** 共享 registry 条目、由其派生的 help/catalog/Telegram 菜单、Gateway 冷路径与
busy-agent 快路径、`_handle_delegate_command` 与命令专用的 `_delegate_delivery_for`、
`gateway/sachima_delegate_selector.py`、`gateway/sachima_delegate_policy.py`、六条命令专用文案
（usage / unavailable / refused / unverified-selector / unknown-selector / ambiguous）以及
`requested_profile_id` 全部移除，没有兼容垫片、弃用提示或迁移分支。`tests/gateway/test_feishu.py`
中的 `/delegate` 只是通用 mention 用例的样本文本，已替换为一个仍然存在的命令词，断言与行为不变。
语义路径的投递构造保留在 `GatewayRunner._delegate_delivery_from_origin`（restoration 与 observer 用的那一个）。

### 阶段 4：回归闭环与文档对账

将命令测试拆为语义控制/执行 preset 测试；保留并继续运行 coordinator、state、result、restoration、delivery 和 result-context 测试。实现完成后检查维护中的用户文档/help；历史日期计划保留为历史证据，不反向改写。

验收还须复核阶段 0 基线：工程型路由的 sealed grant 与生效授权逐项相等、无 permission violation、子进程回收、评审型 task 的 pre/post 工作区 guard 相等；实施型路由另须复核那次 benign 写入证明（期望工作区 delta 逐项相等、清理/回滚证据），只读路由不要求写入证明。以注入式 fixture 与本地 harness 断言，不因此引入 live 或 default-on 路径，也不额外新增产品阶段。

仅当实际源码真相改变路线图状态时，才在后续实施中更新 `docs/roadmap/current-status.md`；仅当产品目标确实改变时更新 `GOAL.md`。同时检查 `docs/sachima-channel.md`、网站/help/catalog 等维护面。

**实施结论（已完成）：** `tests/gateway/test_sachima_delegate_selection.py` 删除；
`tests/gateway/test_sachima_delegate_command.py` 更名为 `test_sachima_delegate_gateway.py`，注册测试改写为
缺席测试，命令驱动改为"admit + coordinator.create"的语义驱动，其余（投递、平台 call shape、结果上下文交接、
恢复屏障）保持不变并继续通过。新增 `test_sachima_agent_execution_presets.py` 与
`test_sachima_delegate_control_tool.py`。`docs/roadmap/current-status.md` 增加一行当前任务状态并补充
非批准项；产品目标未变，`GOAL.md` 未改。维护面复核结果：没有任何用户/help/channel 文档记载过
`/delegate`（`docs/sachima-channel.md` 不存在，website 文档中的 `delegate` 均指通用
`tools/delegate_tool.py` 子代理能力），因此无需改写。

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

- 新增 semantic-control、roster-contract、execution-preset 测试
  （`test_sachima_agent_execution_presets.py`、`test_sachima_delegate_control_tool.py`、
  `test_arsd_socket_contract.py` 的 `agent_list` 段、`test_arsd_supervisor_backend.py` 的 roster 段）；
- `test_sachima_delegate_coordinator.py`
- `test_sachima_delegate_state.py`
- `test_sachima_delegate_result.py`
- `test_sachima_delegate_gateway.py`（原 `test_sachima_delegate_command.py`）
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
- coordinator/state 的记录种类、版本与目录布局不变；唯一的字段变化是 `profile_id` → `agent_id`
  （canonical 文法，旧值全部落在新文法内），`from_dict` 读取旧键，既有 durable records 无需迁移且持续可读。
- 若新路径回滚，恢复命令代码与相关源码即可；不得保留永久双入口。任何已单独启用的运行时配置须在其独立审批下回退。

## 审批矩阵

| 边界 | 当前状态 | 单独批准后才允许 |
|---|---|---|
| 本计划验收 | 已受理 | — |
| Sachima 源码与测试实施 | 已完成（本地工作区） | — |
| 外部 ARS roster prerequisite | 已交付并锁定（0.7.8 `agent_list`） | — |
| commit / push / PR / merge | 未授权 | 任一仓库历史或远端变更 |
| 运行时配置与功能激活 | 未授权 | preset / role-policy 文件写入、生产 ARS config 增加 `grant_by_policy_ref`、`SACHIMA_AGENT_EXECUTION_PRESETS_FILE` / `SACHIMA_AGENT_ROLE_POLICY_FILE`、toolset/surface 开启或生产写入 |
| `oh-my-pi` 现有权限 preset / 审批模式 | 未授权改动 | 任何对其生产授权面的修改 |
| Gateway restart / deploy | 未授权 | 重启、重载、部署或生产流量接入 |
| live multi-agent canary | 未授权 | 真实 ARS、IM、provider 或 AGENT 执行与证据采集 |
