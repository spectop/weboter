# Agent 协作接口文档

> 目的：把 Weboter 作为多人（多 agent）协作项目运行，确保每个 agent 有清晰职责，并通过标准交接包沟通。

## 1. 角色与职责边界

| 角色 | 主要模块 | 强项 | 不负责 |
| --- | --- | --- | --- |
| Core Agent | `public/` + `core/` | 契约、执行链路、分层边界 | UI 交互细节 |
| Service Agent | `app/service.py` + `app/routers/` | HTTP/CLI 接口、错误语义、返回规模 | 前端展示逻辑 |
| MCP Agent | `mcp/server.py` | 工具面、profile 权限、输出裁剪 | 执行引擎内部实现 |
| Panel Agent | `app/panel/` + `routers/panel.py` | 前端结构、页面交互、panel 路由 | core 契约设计 |
| Plugin Agent | `core/plugin_loader.py` + 插件包 | 插件导出契约、加载机制、zip 安全 | 业务 UI |

## 2. 协作前置规则（强制）

1. 改动前先读取对应接口文档：`doc/interfaces/<module>.md`。
2. 若改动跨模块，先确定“主责 agent”与“协作 agent”。
3. 任何跨模块可见变更，先更新接口文档再改实现。

## 3. 交接包（Handoff Package）

跨 agent 协作必须使用统一交接包，避免口头约定。

```markdown
# Handoff Package
## 任务来源
- from_agent:
- to_agent:
- task_id:

## 背景与目标
- 目标:
- 非目标:

## 接口约束
- 关联文档:
- Stable 接口:
- Evolving 接口:

## 输入
- 上游已完成:
- 可复用数据/文件:
- 前置条件:

## 输出要求
- 需要产出:
- 验收标准:

## 兼容性
- 破坏性变更: yes/no
- 迁移方案:

## 风险与回滚
- 风险点:
- 回滚方案:
```

## 4. 沟通层级

- L1：同模块内调整
  - 仅主责 agent 执行，完成后更新模块接口文档。
- L2：双模块联动
  - 主责 agent 提交交接包，协作 agent 只处理本模块边界。
- L3：全链路变更
  - `architecture-reviewer` 先给边界评估，再拆分任务给各模块 agent。

## 5. 前端/后端/插件协作约定

- 前端（Panel）向后端（Service）提需求：
  - 只能提接口契约诉求，不指定后端实现细节。
  - 必须给出字段级验收标准。
- 后端（Service/MCP）向前端回传：
  - 给出稳定字段、默认值、错误码语义。
  - 给出分页/窗口默认值，防止大结果冲击 UI。
- 插件（Plugin）与后端协作：
  - 插件只通过 contracts 暴露能力。
  - Service/MCP 只依赖 catalog 摘要与单项 detail，不依赖插件内部实现。

## 6. 完成定义（DoD）

1. 模块内实现完成且边界未越权。
2. 相关接口文档已更新。
3. 交接包的输出要求全部满足。
4. 验证记录可追溯（至少包含接口/行为验证结论）。
