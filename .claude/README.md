# Weboter Agent / Skill 分工

本目录用于沉淀模块化协作规则。

## Agent 列表

- `agents/core-boundary-guardian.md`
- `agents/service-surface-owner.md`
- `agents/mcp-contract-operator.md`
- `agents/panel-shell-steward.md`
- `agents/plugin-integration-maintainer.md`
- `agents/architecture-reviewer.md`

## Skill 列表

- `skills/core-contract-first/SKILL.md`
- `skills/service-interface-keeper/SKILL.md`
- `skills/mcp-surface-governance/SKILL.md`
- `skills/panel-modularization/SKILL.md`
- `skills/plugin-contract-governance/SKILL.md`
- `skills/project-guide/SKILL.md`

## 强制规则

1. 处理模块任务前，先读对应接口文档：`doc/interfaces/*.md`。
2. 任何对外接口变更先改文档再改代码。
3. 如果改动跨模块，至少同步更新两个模块的接口文档。

## 多 Agent 协作

- 协作协议文档：`doc/interfaces/agent-collaboration.md`
- 跨模块任务必须由主责 agent 生成 Handoff Package，再交给协作 agent。
- 协作 agent 只处理本模块边界，禁止跨边界“顺手修改”。

推荐分工：

- 前端：`panel-shell-steward`
- 后端接口：`service-surface-owner`
- MCP 工具面：`mcp-contract-operator`
- 插件开发：`plugin-integration-maintainer`
- 架构审计：`architecture-reviewer`
