# Weboter 文档索引

本文档作为 `doc/` 总入口，按“使用 -> 架构 -> 接口 -> 规划”的顺序组织。

## 1. 使用文档

- 工作流格式说明：`workflow.md`
- Service 与 CLI 说明：`service_usage.md`

## 2. 架构文档

- 执行引擎架构：`design/engine_architecture.md`
- Service / Client / MCP 架构：`design/mcp_architecture.md`

## 3. 对外接口文档（重点）

所有面向其他模块复用的能力，必须先落到接口文档，再允许实现改动。

- 接口文档总览：`interfaces/README.md`
- Core 对外接口：`interfaces/core.md`
- Service 对外接口：`interfaces/service.md`
- MCP 对外接口：`interfaces/mcp.md`
- Panel 对外接口：`interfaces/panel.md`
- Plugin 对外接口：`interfaces/plugin.md`

## 4. 计划与样例

- 开发计划：`development_plan.md`
- MCP 导入样例：
  - `mcp.weboter.json`
  - `mcp.weboter.windows-wsl.json`
  - `mcp.weboter.windows-pipx.json`
  - `mcp.weboter.windows-uvx.json`

## 5. 文档维护规则

- 接口文档描述的是“跨模块契约”，不是实现细节。
- 若接口语义、字段、默认值、错误模型发生变化，必须同步更新对应接口文档。
- 所有 agent / skill 处理模块任务时，应先读取本模块接口文档，再开始编码。
