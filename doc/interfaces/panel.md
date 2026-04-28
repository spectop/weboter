# Panel 对外接口文档

> 模块位置：`weboter/app/panel/`、`weboter/app/routers/panel.py`

## 1. 边界定义

Panel 是 Service 的 Web 管理入口，包含：

- 页面壳：`/panel`
- 静态资源：`/panel/assets/*`
- 面板 API：`/panel/api/*`
- 子路径 SPA 入口：`/panel/{panel_path:path}`（兜底）

## 2. 路由契约（Stable）

### 2.1 页面与资源

- `GET /panel`
- `GET /panel/assets/{asset_path:path}`
- `GET /panel/{panel_path:path}`

约束：

- `panel_subpage` 必须位于所有 `/panel/api/*` 路由之后，避免通配路由抢占 API。
- `assets` 需根据后缀返回正确 media type。

### 2.2 鉴权与用户

- `GET /panel/api/status`
- `POST /panel/api/login`
- `POST /panel/api/logout`
- `GET /panel/api/me`

### 2.3 业务 API（与 service 能力对齐）

- env：`/panel/api/env*`
- plugin：`/panel/api/plugins*`
- overview：`/panel/api/overview`
- task：`/panel/api/tasks*`
- session：`/panel/api/sessions*`
- workflow：`/panel/api/workflows*`

### 2.4 workflow 展示接口（Evolving）

- `GET /panel/api/workflows`
	- 用途：列出当前受管目录 workflow 名称。
	- 返回关键字段：
		- `directory`: string，当前 workflow 目录绝对路径。
		- `items`: string[]，workflow 逻辑名列表（不带 `.json`）。
		- `workflows`: object[]，用于页面展示的 workflow 列表，结构为：
			- `workflow`: string，workflow 逻辑名。
			- `name`: string，workflow 展示名（优先 flow.name，回退逻辑名）。
- `GET /panel/api/workflows/{workflow_name}`
	- 用途：读取单个 workflow 详情用于节点展示。
	- 返回关键字段：
		- `name`: string，请求的 workflow 逻辑名。
		- `path`: string，实际解析后的 workflow 文件路径。
		- `flow`: object，Flow dataclass 的 JSON 结构（含 `nodes`）。
- `POST /panel/api/workflows/{workflow_name}/create-task`
	- 用途：从当前 workflow 直接创建执行任务（用于画布工具栏 “创建 task”）。
	- 返回关键字段：
		- `workflow`: string，workflow 逻辑名。
		- `resolved`: string，解析后的 workflow 文件路径。
		- `task`: object，任务对象（task_id、status、workflow_path 等）。
- `PUT /panel/api/workflows/{workflow_name}`
	- 用途：保存 workflow 编辑结果（包含 flow 属性、node 配置、node 新增/删除后的整体结构）。
	- 请求关键字段：
		- `flow`: object，Flow dataclass 的 JSON 结构（`flow_id`、`name`、`description`、`start_node_id`、`nodes`、`sub_flows`、`log`）。
	- 返回关键字段：
		- `workflow`: string，workflow 逻辑名。
		- `path`: string，写回的 workflow 文件路径。
		- `updated`: boolean，固定为 true。
		- `flow`: object，保存后的 Flow dataclass 结构。
- `DELETE /panel/api/workflows/{workflow_name}`
	- 用途：删除 workflow 文件（用于 workflow 工具栏删除）。
	- 返回关键字段：
		- `workflow`: string，workflow 逻辑名。
		- `deleted`: string，被删除的 workflow 文件路径。

## 3. 静态资源契约（Stable）

- 入口 HTML：`weboter/app/panel/static/index.html`
- 样式：`weboter/app/panel/static/assets/panel.css`
- 脚本：`weboter/app/panel/static/assets/panel.js`

打包约束：

- wheel 必须包含以上三个资源路径。
- 若新增资源子目录，需同步更新 `pyproject.toml` package-data。

## 4. 前后端边界（Evolving）

- 前端仅通过 `/panel/api/*` 访问数据。
- 禁止前端直接依赖非 panel 命名空间接口。
- 新工作区（如 `panel/settings`）若新增接口，必须先登记到本文件。

## 5. 变更要求

下列变更必须先更新本文件：

- panel 路由模式变化
- 登录态字段变化
- `/panel/api/*` 返回结构关键字段变化
- 静态资源入口与路径变化
