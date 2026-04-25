# MCP 对外接口文档

> 模块位置：`weboter/mcp/server.py`

## 1. 边界定义

MCP adapter 只负责把 MCP 工具调用转发到远程 service，不承载执行引擎。

## 2. 稳定入口（Stable）

- 工厂函数：`create_mcp_server() -> FastMCP`
- 连接依赖：`_build_client()` 从配置读取 `WEBOTER_SERVICE_URL` / token

约束：

- 未配置 service URL 时必须快速失败，不允许隐式本地执行。

## 3. 工具权限模型（Stable）

通过 profile 控制可用工具集合：

- `readonly`
- `operator`
- `admin`

约束：

- 新增工具必须声明所属 profile。
- 高风险工具不得进入 `readonly`。

## 4. 工具分组契约（Stable）

- service 观测：`service_*`
- env 管理：`env_*`
- catalog：`action_*` / `control_*` / `plugin_refresh`
- workflow：`workflow_*`
- task：`task_*`
- session：`session_*`

## 5. 输出约束（Stable）

- 默认小窗口返回：列表/日志需限制默认数量。
- 渐进式披露：先摘要，再 detail。
- 可继续获取指引：返回中应包含 total、remaining 或 detail 入口提示。

## 6. Prompt 契约（Evolving）

MCP 内置 prompt：

- `quickstart`
- `debug_playbook`
- `tool_selection`

约束：

- prompt 文案变更不得改变工具语义，只能优化调用引导。

## 7. 变更要求

下列变更必须先更新本文件：

- 工具名、参数、默认值或返回摘要结构变更
- profile 权限矩阵变更
- 输出裁剪策略变更
