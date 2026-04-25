# Weboter 模块接口总览

本目录定义 Weboter 的跨模块接口契约。

## 适用范围

以下模块是当前必须维护独立接口文档的边界：

- Core
- Service
- MCP
- Panel
- Plugin

## 文档清单

- `core.md`：核心执行层对外能力（契约层、插件加载、执行入口）
- `service.md`：HTTP/CLI 访问面的稳定能力与错误边界
- `mcp.md`：MCP 工具集、权限 profile 与输出约束
- `panel.md`：Panel 路由、前端资源与前后端交互边界
- `plugin.md`：插件包结构、注册规则、加载与发布约束
- `agent-collaboration.md`：多 agent 职责边界、交接包格式与跨模块沟通协议

## 兼容性分级

- Stable：可被外部模块直接依赖；变更需要兼容方案和迁移说明。
- Evolving：允许小幅调整；变更需要记录 release note。
- Internal：仅内部实现可用，禁止跨模块引用。

## 变更流程（强制）

1. 先改接口文档（本目录）并标注影响范围。
2. 再改实现代码。
3. 最后更新 README / CLAUDE / agent/skill 中的引用。

未同步接口文档的实现改动视为不完整改动。
