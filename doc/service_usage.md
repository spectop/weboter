# Weboter Service 使用参考

本文档收纳 `weboter service`、`weboter client` 与本地运行模式的详细操作说明，作为 README 的参考补充。

## Service 命令

启动后台 service：

```bash
weboter service start
```

查看 service 状态：

```bash
weboter service status
weboter service status --json
```

停止后台 service：

```bash
weboter service stop
```

查看系统日志：

```bash
weboter service logs --lines 100
```

默认情况下，service 会把状态写入 `.weboter/service.json`；如果在 `weboter.yaml` 中固定了 `service.port`，后续 `weboter client` 或脚本可以稳定连接到该地址。

## Workflow 命令

上传一个 workflow 到本地 service 托管目录：

```bash
weboter workflow --upload workflows/demo_empty.json
```

上传并立即执行：

```bash
weboter workflow --upload workflows/demo_empty.json --execute
```

提交时直接要求在第一个节点前停住：

```bash
weboter workflow --dir workflows --name demo_empty --execute --pause-before-start
```

提交时预设断点：

```bash
weboter workflow --dir workflows --name demo_empty --execute --breakpoints '[{"phase":"before_step","node_id":"login"}]'
```

如果通过 HTTP API 或 MCP 提交执行，也可以在提交时直接附带调试预设：

- `pause_before_start: true`：要求第一个节点执行前先停住
- `breakpoints: [...]`：在 session 创建时就装载断点，不必等任务开始后再补发

递归列出目录中的 workflow：

```bash
weboter workflow --dir workflows --list
```

从指定目录解析并执行某个 workflow：

```bash
weboter workflow --dir workflows --name demo_empty --execute
weboter workflow --dir workflows --name pack_a.pack_b.do_sth --execute
```

等待执行完成：

```bash
weboter workflow --dir workflows --name demo_empty --execute --wait
```

以 JSON 返回机器可读结果：

```bash
weboter workflow --dir workflows --name demo_empty --execute --json
```

## Task 命令

```bash
weboter task list
weboter task get <task_id>
weboter task show <task_id>
weboter task logs <task_id> --lines 100
weboter task wait <task_id>
```

`task_id` 支持唯一前缀匹配。

`task get` 是与 MCP `task_get` 对齐的新命令名，`task show` 仍保留为兼容别名。

## Session 命令

CLI 现在提供与 MCP `session_*` 基本对应的会话操作入口：

```bash
weboter session list
weboter session get <session_id>
weboter session snapshots <session_id> --limit 10
weboter session snapshot-detail <session_id> --snapshot-index 0 --sections runtime,page
weboter session workflow <session_id>
weboter session workflow-node-detail <session_id> --node-id login
weboter session runtime-value <session_id> --key '$flow{form}'
weboter session update-breakpoints <session_id> --breakpoints '[{"phase":"before_step","node_id":"login"}]'
weboter session interrupt <session_id>
weboter session resume <session_id>
weboter session page-snapshot <session_id>
weboter session page-run-script <session_id> --code @script.py --arg '{"mode":"debug"}'
```

复杂参数统一支持两种写法：

- 直接传 JSON 字符串
- 传 `@文件路径`，由 CLI 读取文件内容后再解析

## 本地模式

如果需要临时绕过后台 service，可使用本地模式：

```bash
weboter workflow --dir workflows --name demo_empty --execute --local
```

## 鉴权

如果希望启用 service 鉴权，可在 `weboter.yaml` 中配置：

```yaml
service:
  auth:
    enabled: true
    token:
```

当 `service.auth.enabled: true` 且未手动填写 `token` 时，Weboter 会在第一次成功启动时自动生成 token，并在当前 Terminal 输出一次 secret 提示；之后不会重复显示。此时除 `/health`、`/docs` 和 `/openapi.json` 外，其余接口都要求请求头 `X-Weboter-Token`。

## HTTP 接口概览

service 默认暴露以下接口：

- `GET /health`：存活检查
- `GET /service/state`：读取 service 元数据
- `GET /service/logs`：读取系统日志
- `GET /catalog/actions` / `GET /catalog/actions/{full_name}`：读取 action 摘要与单项参数契约
- `GET /catalog/controls` / `GET /catalog/controls/{full_name}`：读取 control 摘要与单项参数契约
- `POST /workflow/upload`：上传并可选执行 workflow
- `POST /workflow/dir`：列举、解析或执行目录中的 workflow
- `GET /tasks` / `GET /tasks/{task_id}` / `GET /tasks/{task_id}/logs`：任务查看与日志读取
- `GET /sessions` / `GET /sessions/{session_id}` / `GET /sessions/{session_id}/snapshots`：执行会话观察
- `POST /sessions/{session_id}/pause|interrupt|resume|abort`：执行会话控制，其中 `interrupt` 会在下一个节点执行前停住
- `POST /sessions/{session_id}/context|jump|patch-node|add-node`：运行中介入 workflow
- `GET /sessions/{session_id}/workflow`：读取当前执行中的 workflow 定义
- `POST /sessions/{session_id}/breakpoints` / `POST /sessions/{session_id}/breakpoints/clear`：配置或清理断点
- `GET /sessions/{session_id}/page`、`POST /sessions/{session_id}/page/script` 及其他 `page/*` 接口：页面级调试与操作
- `GET /openapi.json` / `GET /docs`：API 描述与调试入口

### 推荐的调试组合

针对 agent 调试，当前推荐的最小组合是：

- `catalog/actions` / `catalog/controls`：先确认环境里可用的 action / control，再按单项读取参数契约
- `pause_before_start`：在提交 workflow 时直接要求第一个节点前停住，适合首轮调试
- `interrupt`：请求在下一个节点执行前停住，适合会话已经启动后的追加介入
- `breakpoints`：按 `before_step + node_id` 或 `node_name` 配置精确断点
- `workflow`：直接读取当前会话里的 workflow 定义，便于决定 patch/add/jump
- `page/script`：以受控 Python 代码执行 Playwright 页面操作，替代 MCP 暴露大量 `click/fill/...` 离散工具

`page/script` 会使用受限内建函数、禁止 `import` / `global` / 双下划线访问，并带超时控制；执行后会返回脚本结果、最新页面快照以及额外生成的 HTML / 截图文件路径。

## 相关参考

- workflow 格式说明： [doc/workflow.md](doc/workflow.md)
- service / client / mcp 架构： [doc/design/mcp_architecture.md](doc/design/mcp_architecture.md)
- 开发计划： [doc/development_plan.md](doc/development_plan.md)