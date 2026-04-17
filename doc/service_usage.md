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
weboter task show <task_id>
weboter task logs <task_id> --lines 100
weboter task wait <task_id>
```

`task_id` 支持唯一前缀匹配。

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
- `POST /workflow/upload`：上传并可选执行 workflow
- `POST /workflow/dir`：列举、解析或执行目录中的 workflow
- `GET /tasks` / `GET /tasks/{task_id}` / `GET /tasks/{task_id}/logs`：任务查看与日志读取
- `GET /sessions` / `GET /sessions/{session_id}` / `GET /sessions/{session_id}/snapshots`：执行会话观察
- `POST /sessions/{session_id}/pause|resume|abort`：执行会话控制
- `POST /sessions/{session_id}/context|jump|patch-node|add-node`：运行中介入 workflow
- `GET /sessions/{session_id}/page` 及相关 `POST` 接口：页面级操作
- `GET /openapi.json` / `GET /docs`：API 描述与调试入口

## 相关参考

- workflow 格式说明： [doc/workflow.md](doc/workflow.md)
- service / client / mcp 架构： [doc/design/mcp_architecture.md](doc/design/mcp_architecture.md)
- 开发计划： [doc/development_plan.md](doc/development_plan.md)