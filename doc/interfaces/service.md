# Service 对外接口文档

> 模块位置：`weboter/app/service.py`、`weboter/app/routers/`

## 1. 边界定义

Service 是唯一执行控制面，负责：

- workflow 上传/解析/执行
- task 与 session 管理
- env 管理
- 插件目录与 catalog 暴露
- panel 与 mcp 共享的 HTTP 接口

## 2. Python 服务接口（Evolving）

核心对象：`WorkflowService`

关键方法：

- 工作流
  - `upload_workflow(source)`
  - `resolve_from_directory(directory, workflow_name=None)`
  - `list_directory_workflows(directory)`
  - `update_workflow(directory, workflow_name, flow_data)`
  - `delete_workflow(directory, workflow_name=None)`
  - `run_workflow(workflow_path, logger=None, hooks=None)`
- 环境变量
  - `list_env(group=None)`
  - `env_tree(group=None)`
  - `get_env(name, reveal=False)`
  - `set_env(name, value)`
  - `delete_env(name)`
  - `import_env(payload, replace=False)`
  - `export_env(group=None, reveal=False)`
- 能力目录
  - `list_actions()` / `get_action(full_name)`
  - `list_controls()` / `get_control(full_name)`
  - `list_plugins()` / `refresh_plugins()`
  - `install_plugin_archive(source, replace=True)`

## 3. HTTP 接口族（Stable）

### 3.1 Service / 系统

- `GET /health`
- `GET /service/state`
- `GET /service/logs`
- `GET /service/processes`

### 3.2 Env

- `GET /env`
- `GET /env/tree`
- `GET /env/export`
- `POST /env/import`
- `GET /env/{name}`
- `POST /env`
- `DELETE /env/{name}`

### 3.3 Catalog / Plugin

- `GET /catalog/actions`
- `GET /catalog/actions/{full_name}`
- `GET /catalog/controls`
- `GET /catalog/controls/{full_name}`
- `POST /catalog/refresh`

### 3.4 Workflow

- `POST /workflow/upload`
- `POST /workflow/dir`
- `DELETE /workflow/dir`
- `PUT /panel/api/workflows/{workflow_name}`（panel 工作流编辑保存）
- `DELETE /panel/api/workflows/{workflow_name}`（panel workflow 删除）

### 3.5 Task / Session

- `GET /tasks`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/logs`
- `GET /sessions`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/snapshots`
- `POST /sessions/{session_id}/pause|interrupt|resume|abort`
- `POST /sessions/{session_id}/context|jump|patch-node|add-node|run-node`
- `GET /sessions/{session_id}/workflow`
- `POST /sessions/{session_id}/breakpoints`
- `POST /sessions/{session_id}/breakpoints/clear`
- `GET /sessions/{session_id}/page`
- `POST /sessions/{session_id}/page/script`

## 4. 错误模型

- 参数错误：400
- 未授权：401/403
- 资源不存在：404
- 业务异常：按统一 `raise_http_error` 映射

约束：

- 新接口必须进入 OpenAPI，并在本文件登记所属接口族。

## 5. 兼容约束

- CLI 与 MCP 共同依赖 HTTP 层语义，不允许对已发布路径做无迁移变更。
- 列表与日志接口必须保守默认值，避免大结果默认返回。

## 6. 变更要求

下列变更必须先更新本文件：

- HTTP 路径/方法变更
- 关键请求字段变更（如 `pause_before_start`、`breakpoints`）
- task/session 状态语义变更
