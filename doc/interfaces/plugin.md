# Plugin 对外接口文档

> 模块位置：`weboter/core/plugin_loader.py`、插件包目录

## 1. 边界定义

Plugin 是 Core 扩展点，负责注入 action/control，不直接接入 service 或 panel 内部实现。

## 2. 插件模块契约（Stable）

每个插件模块必须导出：

- `package_name: str`
- `actions: list[type[ActionBase]]`
- `controls: list[type[ControlBase]]`

约束：

- `package_name` 必须非空。
- `actions` 与 `controls` 至少一项非空。
- 列表元素必须是契约基类子类。

## 3. 插件发现机制（Evolving）

### 3.1 目录插件

- 路径：`paths.PLUGIN_ROOT` 下每个子目录
- 子目录必须包含 `__init__.py`

### 3.2 安装插件

- entry point：`weboter.plugins`
- 或符合 `weboter-*` 分发自动发现规则

## 4. 刷新与可观测性（Stable）

- 刷新入口：`refresh_plugins()`
- 快照入口：`get_plugin_snapshot()`

返回摘要至少包含：

- `loaded` / `loaded_count`
- `errors` / `error_count`
- `plugin_root`

## 5. 上传包契约（Stable）

Panel/Service 上传插件 zip 时必须满足：

- 仅支持 `.zip`
- 根目录包含 `__init__.py`，或单顶层目录 + `__init__.py`
- 禁止非法路径（目录穿越）

## 6. 开发与兼容要求

- 插件只能依赖 public contracts，禁止耦合 app/service/mcp 内部对象。
- 插件加载失败不应导致 builtin 整体不可用。
- 新增插件能力若影响 catalog 字段，必须同步更新 `doc/interfaces/service.md` 和 `doc/interfaces/mcp.md`。

对于依赖较重的能力（例如 OCR、视觉验证码、机器学习推理），优先以插件形式提供，而不是继续扩大 builtin 依赖面。推荐做法：

- builtin 仅保留轻量且高度通用的基础能力。
- 重依赖能力通过目录插件或 `weboter.plugins` entry point 注入。
- 插件缺失依赖时，应只影响该插件本身，不影响 builtin 与其他插件加载。

## 7. 变更要求

下列变更必须先更新本文件：

- 插件导出字段约定变化
- 插件发现顺序与优先级变化
- 插件刷新返回结构变化
- 上传 zip 校验规则变化
