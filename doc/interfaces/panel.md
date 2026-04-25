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
