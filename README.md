# Weboter

Weboter 是一个配置驱动的网页自动化框架。当前阶段优先交付一个可在 Linux/WSL 环境运行的 workflow service，让用户可以直接上传 workflow 文件或指定 workflow 目录，并通过 CLI 执行。

## 当前能力

- 使用 JSON 描述 workflow
- 通过 `Executor` 执行节点和控制流
- 支持基于 FastAPI/uvicorn 的本地后台 service
- 支持 `weboter service start` 启动本地后台 service
- 支持 CLI 作为 client，把 workflow 文件或目录路径发送给后台 service
- 支持 OpenAPI 文档、结构化 JSON 输出和 stdio MCP adapter
- 支持后台任务执行、任务状态查看、任务日志查看和系统日志查看
- 支持执行会话快照、暂停/恢复、运行时上下文修改和页面级介入
- 支持基础内置动作与控制，不依赖验证码相关可选包也能运行基础流程

## 安装

如果你只需要从客户端启动 MCP adapter，或只需要 HTTP / MCP 远程访问能力，可以安装轻量基础包：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

这个轻量安装不会包含 FastAPI / uvicorn / Playwright，因此不会在 `uvx` / `pipx` 启动 `weboter-mcp` 时把浏览器执行环境一起拉下来。

如果你需要本地启动 Weboter service、执行 workflow，或使用 `--local` 模式，再安装 service 依赖：

```bash
python -m pip install -e '.[service]'
playwright install chromium
```

如果需要浏览器伪装或验证码相关动作，再追加可选依赖：

```bash
python -m pip install -e '.[service,browser]'
python -m pip install -e '.[service,captcha]'
```

默认情况下，Weboter 会优先读取仓库根目录下的 `weboter.yaml` 作为统一配置文件；如果需要使用其他位置的配置文件，可以通过 `weboter --config /path/to/weboter.yaml ...` 指定。仓库根目录现在提供了一份默认样例 [weboter.yaml](weboter.yaml)。

但对于 MCP 导入场景，推荐不要依赖配置文件，而是直接在 MCP JSON 里通过 `env` 传入少量连接参数。外部 `weboter-mcp` / `python -m weboter.mcp.server` 只负责连接已经启动的 Weboter service，不负责启动本地 service，也不依赖 service 的工作目录。

当前建议通过配置文件统一管理这些运行时配置：

- `paths.workspace_root`：工作区根目录
- `paths.data_root`：service 状态、日志、secret 持久化目录
- `paths.workflow_store`：service 托管 workflow 目录
- `service.host` / `service.port`：service 监听地址与端口
- `service.auth.enabled` / `service.auth.token`：是否启用接口鉴权以及固定 token
- `mcp.service_url` / `mcp.profile` / `mcp.transport`：MCP adapter 连接的 service、权限档位和传输方式
- `client.api_token` / `client.caller_name` / `client.request_timeout`：CLI / MCP client 的默认请求行为

## 使用

启动后台 service：

```bash
weboter service start
```

默认会自动选择一个空闲本地端口，并把连接信息写入 `.weboter/service.json`；如果你在 `weboter.yaml` 里固定了 `service.port`，则后续 CLI / MCP 会直接使用那组配置或这个状态文件。

service 启动后会暴露：

- `GET /health` 用于存活检查
- `GET /service/state` 用于读取当前 service 元数据
- `GET /service/logs` 用于读取系统日志
- `POST /workflow/upload` 用于上传并可选执行 workflow
- `POST /workflow/dir` 用于列举、解析或执行目录中的 workflow
- `GET /tasks` / `GET /tasks/{task_id}` / `GET /tasks/{task_id}/logs` 用于任务查看和日志读取
- `GET /sessions` / `GET /sessions/{session_id}` / `GET /sessions/{session_id}/snapshots` 用于执行会话观察
- `POST /sessions/{session_id}/pause|resume|abort` 用于执行会话控制
- `POST /sessions/{session_id}/context|jump|patch-node|add-node` 用于运行中介入 workflow
- `GET /sessions/{session_id}/page` 与页面相关 `POST` 接口用于 Playwright 页面操作
- `GET /openapi.json` 和 `GET /docs` 用于 API 描述和调试

查看 service 状态：

```bash
weboter service status
```

如果需要供脚本、agent 或 MCP wrapper 稳定消费，可以直接使用 JSON 输出：

```bash
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

上传一个 workflow 到本地 service 目录：

```bash
weboter workflow --upload workflows/demo_empty.json
```

上传并立即执行：

```bash
weboter workflow --upload workflows/demo_empty.json --execute
```

从指定目录递归列出 workflow：

```bash
weboter workflow --dir workflows --list
```

返回结果只包含 service 感知的 workflow 逻辑名，不包含 `.json` 后缀。多层目录会映射为点号形式，例如 `pack_a/pack_b/do_sth.json` 会显示为 `pack_a.pack_b.do_sth`。

从指定目录解析并执行一个 workflow：

```bash
weboter workflow --dir workflows --name demo_empty --execute
```

如果 workflow 位于多层目录中，则使用点号名进行操作：

```bash
weboter workflow --dir workflows --name pack_a.pack_b.do_sth --execute
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

`service status`、`workflow ... --execute`、`task show`、`task list`、`task logs` 这些命令也都支持 `--json` 输出。

如果你想临时绕过后台 service，仍然可以用本地模式：

```bash
weboter workflow --dir workflows --name demo_empty --execute --local
```

当 service 已停止时，`weboter service logs`、`weboter task list` 和 `weboter task logs` 仍然会直接读取 `.weboter/` 下的本地历史文件，方便排查问题。

如果希望启用 service 鉴权，可以在 `weboter.yaml` 中打开：

```yaml
service:
	auth:
		enabled: true
		token:
```

当 `service.auth.enabled: true` 且未手动填写 `token` 时，Weboter 会在第一次成功启动时自动生成 token，并在当前 Terminal 输出一次 secret 提示；之后不会重复显示。此时除 `/health`、`/docs` 和 `/openapi.json` 外，其余接口都要求请求头 `X-Weboter-Token`。

## 示例 workflow

仓库提供了一个不访问外部站点的最小示例：`workflows/demo_empty.json`。

这个 workflow 只执行 `builtin.EmptyAction`，用于验证 CLI、workflow 解析和执行链路是否可用。

## 路线图

1. 补齐 FastAPI service-client 与任务管理的自动化测试
2. 增加任务取消、重试和并发限制配置
3. 补齐 MCP adapter、会话控制和权限边界的自动化测试
4. 增强会话快照内容与权限粒度
5. 增加目录监听模式和可视化 workflow 编辑界面

## Service / MCP 方向

当前实现把职责拆成三层：

- `ExecutionSession` 负责节点级快照、guard、暂停恢复和运行时介入
- FastAPI service 负责稳定的 HTTP/JSON API 和鉴权边界
- `weboter.mcp.server` 负责 stdio MCP tool 暴露，并远程调用 Weboter service

从客户端启动 MCP 的角度，当前更合理的划分不是再增加一个重型的本地 `mcp-srv`，而是把发布与依赖面拆开：

- `weboter service` 继续作为重执行面，持有 FastAPI、Playwright 和 workflow 运行时
- `weboter-mcp` 保持为轻量 stdio adapter，只保留 `mcp + HTTP client`

也就是说，当前需要拆的是“轻客户端安装面”和“重执行端安装面”，而不是再把 MCP 角色额外拆成一套新的重型 server / cli 双进程。

推荐的跨环境调用链是：

1. Agent 通过 MCP client 拉起 `weboter.mcp.server`
2. MCP adapter 使用 `WEBOTER_SERVICE_URL` 或 `mcp.service_url` 连接目标 Weboter service
3. Weboter service 将控制命令下发到对应 `ExecutionSession`

仓库已经提供几份“单 JSON 连接已启动 service”的样例：

- 同环境直接运行 Python module： [doc/mcp.weboter.json](doc/mcp.weboter.json)
- Windows agent 调 WSL 内 Weboter： [doc/mcp.weboter.windows-wsl.json](doc/mcp.weboter.windows-wsl.json)
- Windows `pipx run --spec`： [doc/mcp.weboter.windows-pipx.json](doc/mcp.weboter.windows-pipx.json)
- Windows `uvx --from`： [doc/mcp.weboter.windows-uvx.json](doc/mcp.weboter.windows-uvx.json)

如果 agent 跑在 Windows，而 `weboter` 项目和虚拟环境在 WSL 里，不要直接让 Windows Python 执行 `python -m weboter.mcp.server`。否则会出现 `ModuleNotFoundError: No module named 'weboter'`，因为那个包并没有安装在 Windows 的 Python 环境里。

这种场景下应改为让 agent 调用 `wsl.exe`，再在 WSL 内激活项目虚拟环境并启动 MCP adapter。

如果你希望完全通过 MCP JSON 控制外部 MCP adapter，可以直接在 `env` 中设置：

- `WEBOTER_SERVICE_URL`：已启动 Weboter service 的 HTTP 地址
- `WEBOTER_API_TOKEN`：service 鉴权 token；service 开启鉴权时需要显式传入
- `WEBOTER_MCP_PROFILE` / `WEBOTER_MCP_TRANSPORT` / `WEBOTER_MCP_CALLER_NAME`：MCP adapter 行为

这里有一个边界：外部 MCP adapter 不会帮你生成或读取 service 本地 token，也不会帮你决定 service 的工作区。service 若已开启鉴权，MCP JSON 里应显式提供 `WEBOTER_API_TOKEN`。

当前 MCP profile 的能力边界如下：

- `readonly`: 只读 service、workflow 列表、task、session 和快照
- `operator`: 在只读基础上允许提交 workflow 执行，以及会话控制和页面操作
- `admin`: 在 operator 基础上允许删除受管 workflow、动态加节点和导出修改后的 workflow

这意味着 agent 不再只有观察权限；使用 `operator` 或 `admin` profile 时，已经可以提交 workflow 执行。

## Windows 与免环境启动

`npx` 的体验，本质上是“临时下载包并在隔离环境里运行一个命令”。Python 世界里最接近的是：

- `pipx run`
- `uvx`

如果包已经发布到索引，这两种方式都可以做到只写一段 MCP JSON 就启动，不需要手工创建虚拟环境。

当前阶段 Weboter 还没有发布到 PyPI，因此最实用的方案是：

1. 先构建一个 wheel
2. 在 Windows 上用 `pipx run --spec <wheel>` 或先 `pip install <wheel>` 再运行 `weboter-mcp`

这里的 wheel 现在默认只包含轻量 MCP / HTTP 客户端依赖，不再把 Playwright 一起带到客户端启动路径上。Playwright 应只安装在真正执行 workflow 的 service 所在环境中。

构建 wheel：

```bash
python -m pip wheel . -w dist
```

构建完成后，会在 `dist/` 下得到类似 `weboter-0.1.2-py3-none-any.whl` 的文件。这个 wheel 是纯 Python 包，本身可以跨平台安装；真正的平台差异主要来自依赖和运行时，比如 Playwright 浏览器安装。

如果你希望在 Windows 上直接安装 wheel 后运行：

```powershell
py -m pip install .\weboter-0.1.2-py3-none-any.whl
weboter-mcp
```

如果你希望尽量接近 `npx` 的“无环境一次性运行”，推荐直接使用 `pipx run --spec` 或 `uvx --from`。仓库已提供样例： [doc/mcp.weboter.windows-pipx.json](doc/mcp.weboter.windows-pipx.json) 和 [doc/mcp.weboter.windows-uvx.json](doc/mcp.weboter.windows-uvx.json)

如果你是用本地 wheel 反复迭代调试 MCP，一定要注意 `uvx` / `pipx` 可能复用同版本缓存。最稳妥的方式是每次有行为修复时递增版本号，或显式清理对应缓存环境后再启动。

`bun` / `bunx` 不适合作为当前 Weboter MCP adapter 的直接运行方式，因为 `weboter-mcp` 是 Python entrypoint，不是 Node 包。理论上可以再包一层 Node 启动脚本让 `bun` 去调用外部 `python` 或 `uvx`，但这不会比直接使用 `uvx` 更简单，也不会减少 Python 运行时依赖。因此当前阶段不单独提供 bun 配置样例；如果后续确实需要 bun 入口，更合理的做法是增加一个独立的 Node proxy / launcher。

如果后续要做到真正零前置依赖，合理的下一步不是继续堆 Python 启动参数，而是单独提供一个发布产物，例如：

- 已发布到 PyPI 的 `weboter-mcp` 包，配合 `pipx run` 或 `uvx`
- Windows 单文件 launcher / proxy
- 独立的 `weboter-mcp-proxy` 可执行程序，内部再拉起 Python 包

更完整的架构设计见：[doc/design/mcp_architecture.md](doc/design/mcp_architecture.md)。

## Q&A

### 为什么需要 Weboter，而不是每次都直接用 Agent 自动化？

Agent 的执行过程如果缺少足够强的 harness，结果容易不稳定。把稳定流程沉淀成 workflow 后，可以降低不确定性，也能减少重复调用模型带来的成本。

