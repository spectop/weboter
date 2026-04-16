# Weboter

Weboter 是一个配置驱动的网页自动化框架。当前阶段优先交付一个可在 Linux/WSL 环境运行的 workflow service，让用户可以直接上传 workflow 文件或指定 workflow 目录，并通过 CLI 执行。

## 当前能力

- 使用 JSON 描述 workflow
- 通过 `Executor` 执行节点和控制流
- 支持基于 FastAPI/uvicorn 的本地后台 service
- 支持 `weboter serve start` 启动本地后台 service
- 支持 CLI 作为 client，把 workflow 文件或目录路径发送给后台 service
- 支持 OpenAPI 文档和结构化 JSON 输出，便于后续 agent / MCP 集成
- 支持后台任务执行、任务状态查看、任务日志查看和系统日志查看
- 支持基础内置动作与控制，不依赖验证码相关可选包也能运行基础流程

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
playwright install chromium
```

如果需要浏览器伪装或验证码相关动作，再安装可选依赖：

```bash
python -m pip install -e '.[browser]'
python -m pip install -e '.[captcha]'
```

默认情况下，本地 service 数据目录固定在仓库根目录下的 `.weboter/`。如果你希望改到其他位置，可以设置环境变量 `WEBOTER_HOME`。

## 使用

启动后台 service：

```bash
weboter serve start
```

默认会自动选择一个空闲本地端口，并把连接信息写入 `.weboter/service.json`，后续 `weboter workflow ...` 会自动按这个状态文件连接到后台 service。

service 启动后会暴露：

- `GET /health` 用于存活检查
- `GET /service/state` 用于读取当前 service 元数据
- `GET /service/logs` 用于读取系统日志
- `POST /workflow/upload` 用于上传并可选执行 workflow
- `POST /workflow/dir` 用于列举、解析或执行目录中的 workflow
- `GET /tasks` / `GET /tasks/{task_id}` / `GET /tasks/{task_id}/logs` 用于任务查看和日志读取
- `GET /openapi.json` 和 `GET /docs` 用于 API 描述和调试

查看 service 状态：

```bash
weboter serve status
```

如果需要供脚本、agent 或 MCP wrapper 稳定消费，可以直接使用 JSON 输出：

```bash
weboter serve status --json
```

停止后台 service：

```bash
weboter serve stop
```

查看系统日志：

```bash
weboter serve logs --lines 100
```

上传一个 workflow 到本地 service 目录：

```bash
weboter workflow --upload workflows/demo_empty.json
```

上传并立即执行：

```bash
weboter workflow --upload workflows/demo_empty.json --execute
```

从指定目录列出 workflow：

```bash
weboter workflow --dir workflows --list
```

从指定目录解析并执行一个 workflow：

```bash
weboter workflow --dir workflows --name demo_empty --execute
```

如果希望提交任务后等待执行结束：

```bash
weboter workflow --dir workflows --name demo_empty --execute --wait
```

如果上层调用方需要稳定的机器可读结果，可以启用 `--json`：

```bash
weboter workflow --dir workflows --name demo_empty --execute --json
```

任务管理：

```bash
weboter task list
weboter task show <task_id>
weboter task logs <task_id> --lines 100
weboter task wait <task_id>
```

`task_id` 支持类似 Docker 的唯一前缀匹配，只要前缀能唯一定位任务即可。

`serve status`、`workflow ... --execute`、`task show`、`task list`、`task logs` 这些命令也都支持 `--json` 输出。

如果你想临时绕过后台 service，仍然可以用本地模式：

```bash
weboter workflow --dir workflows --name demo_empty --execute --local
```

当 service 已停止时，`weboter serve logs`、`weboter task list` 和 `weboter task logs` 仍然会直接读取 `.weboter/` 下的本地历史文件，方便排查问题。

## 示例 workflow

仓库提供了一个不访问外部站点的最小示例：`workflows/demo_empty.json`。

这个 workflow 只执行 `builtin.EmptyAction`，用于验证 CLI、workflow 解析和执行链路是否可用。

## 路线图

1. 补齐 FastAPI service-client 与任务管理的自动化测试
2. 增加任务取消、重试和并发限制配置
3. 在当前 JSON CLI 和 HTTP API 之上引入 MCP server
4. 增加目录监听模式和可视化 workflow 编辑界面

## Service / MCP 方向

当前实现把职责拆成三层：

- `WorkflowService` 负责本地业务逻辑，不关心传输层
- FastAPI service 负责稳定的 HTTP/JSON API 和 OpenAPI 描述
- CLI 负责人类可读输出，同时通过 `--json` 提供机器可读输出

这样做的目的，是让后续 agent / MCP 不必复用 CLI 的文本输出解析，而是可以：

1. 直接调用同一个 Python service 层
2. 或复用本地 HTTP API
3. 或在 CLI `--json` 之上做一个轻量 wrapper

对当前阶段来说，CLI 和 service 继续使用本地 loopback HTTP/JSON 已经足够清晰，也更容易过渡到 MCP。真正做 MCP 时，建议把 tool handler 直接接到 `WorkflowService`，而不是反向解析 CLI 文本。喵！

## Q&A

### 为什么需要 Weboter，而不是每次都直接用 Agent 自动化？

Agent 的执行过程如果缺少足够强的 harness，结果容易不稳定。把稳定流程沉淀成 workflow 后，可以降低不确定性，也能减少重复调用模型带来的成本。

