# Weboter MCP 架构设计

## 目标

本阶段的目标不是把 MCP 直接嵌进执行器，而是建立一套稳定的远程控制面，让 agent 能在执行会话中观察、介入、修改并导出 workflow，同时保留权限边界。

## 分层

整体分为三层：

1. `ExecutionSession` 会话层
   - 挂在 `Executor.step_one()` 前后
   - 保存节点级快照
   - 提供暂停、恢复、上下文修改、节点跳转、节点补丁、页面操作的执行入口
   - 在异常时进入 `guard_waiting` 状态，保留第一现场

2. Weboter Service 控制面
   - 基于 FastAPI 暴露任务、会话、日志和页面控制接口
   - session 相关能力通过 HTTP API 远程调用
   - 可通过 `WEBOTER_API_TOKEN` 启用可选鉴权

3. MCP Adapter
   - 基于官方 Python `mcp` SDK 的 `FastMCP`
   - 默认使用 `stdio` 作为 MCP client 到 adapter 的传输方式
   - adapter 再通过 `WEBOTER_SERVICE_URL` 调用 Weboter Service
   - 因此 agent 与 Weboter service 可以不在同一环境

## 执行介入模型

`ExecutionSession` 在以下时机生成快照：

- workflow 加载完成
- 节点执行前
- 节点执行后
- 执行结束
- 执行异常进入 guard

会话支持以下介入动作：

- `pause`
- `resume`
- `abort`
- `set_context`
- `jump_to_node`
- `patch_node`
- `add_node`
- `export_workflow`
- `page_snapshot`
- `page_evaluate`
- `page_goto`
- `page_click`
- `page_fill`

这些动作不会在外部线程直接碰运行中的 Playwright 对象，而是通过会话命令队列回到执行线程自己的事件循环中执行。

## Guard Hook

当 `step_one()` 抛出异常时：

1. `Executor.run()` 调用 session hook 的 `on_error`
2. session 状态切到 `guard_waiting`
3. 当前 runtime、节点、页面状态被快照化
4. 外部 agent 可以读取日志、快照并下发修复命令
5. agent 可选择 `resume` 重试，或 `abort` 失败结束

## 权限边界

本阶段先实现两层边界：

1. Service 侧令牌鉴权
   - 设置 `WEBOTER_API_TOKEN` 后，除 `/health`、`/docs`、`/openapi.json` 外的接口都要求 `X-Weboter-Token`

2. MCP profile
   - `readonly`: 只读任务、会话、日志和快照
   - `operator`: 在只读基础上允许会话控制和页面操作
   - `admin`: 在 operator 基础上允许新增节点和导出修改后的 workflow

## 会话与任务关系

- 一个 task 对应一个 session
- 当前实现中 `session_id == task_id`
- task 保存执行结果和日志路径
- session 保存执行现场、快照、当前节点和可介入状态

## 远程传输说明

`stdio` 只用于 MCP client 与 adapter 进程之间。

真正的跨环境调用链是：

`Agent -> stdio MCP adapter -> HTTP Weboter service -> ExecutionSession`

因此只要 MCP adapter 能访问 `WEBOTER_SERVICE_URL`，agent 和 service 就不必部署在同一环境。

## 客户端启动面的拆分结论

从客户端启动 MCP 的角度，问题的关键不是“要不要再造一个新的 `mcp-srv` 进程”，而是“不要让 stdio adapter 带上执行端依赖”。

当前更合理的拆分是：

- `weboter-mcp` 作为轻量 adapter，只保留 `mcp` 和 HTTP client 能力
- `weboter service` 作为重执行面，持有 FastAPI、Playwright 和 workflow 运行时

因此这里应该拆的是发布物和依赖面，而不是再额外引入一个新的重型 MCP server / CLI 双角色。

如果后续真的需要继续拆分，也应优先考虑：

- 单独发布轻量 `weboter-mcp` 包
- 单独发布执行端 `weboter-service` 包

而不是让客户端启动路径继续携带 Playwright 或浏览器安装逻辑。

## 导出配置

推荐使用如下 MCP 导入方式。

如果 MCP client、Weboter service 和 `weboter` Python 包在同一个环境中，可以直接运行 module：

```json
{
  "mcpServers": {
    "weboter": {
      "command": "python",
      "args": [
        "-m",
        "weboter.mcp.server"
      ],
      "env": {
        "WEBOTER_SERVICE_URL": "http://127.0.0.1:8765",
        "WEBOTER_API_TOKEN": "replace-me",
        "WEBOTER_MCP_PROFILE": "operator"
      }
    }
  }
}
```

如果 agent 跑在 Windows，而 Weboter 运行在 WSL 中，应改为通过 `wsl.exe` 进入 WSL 后再启动 MCP adapter。示例：

```json
{
  "mcpServers": {
    "weboter": {
      "command": "C:\\Windows\\System32\\wsl.exe",
      "args": [
        "-d",
        "Debian",
        "bash",
        "-lc",
        "cd /path/to/weboter && . .venv/bin/activate && WEBOTER_SERVICE_URL=http://127.0.0.1:8765 WEBOTER_MCP_PROFILE=operator python -m weboter.mcp.server"
      ]
    }
  }
}
```

如果 service 未启用 `WEBOTER_API_TOKEN`，不要传空字符串，直接省略该环境变量即可。

## 后续可继续扩展的部分

- 更细粒度的权限作用域，如按 task/session 限制
- 任务取消与回滚
- 页面 DOM diff / HAR / console 等更强快照
- 会话内 workflow 变更的审批与保存策略
- SSE 或 streamable-http 形式的 MCP adapter 部署