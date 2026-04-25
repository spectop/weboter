---
name: mcp-surface-governance
description: "处理 MCP 工具、profile 权限、提示词引导、返回裁剪策略时必须使用。用户提到 mcp/server.py、tool、readonly/operator/admin 时应触发。"
---

# MCP Surface Governance

## 目标

保证 MCP 工具层稳定、权限清晰、默认输出受控。

## 必做步骤

1. 先读取 `doc/interfaces/mcp.md`。
2. 若工具依赖 service 字段，额外读取 `doc/interfaces/service.md`。
3. 校验工具所属 profile 与输出窗口。
4. 先更新接口文档，再改代码与 prompt。
5. 若输出结构变化，向 panel/service 输出 Handoff Package。

## 重点检查

- 新增工具是否声明 profile。
- 默认返回是否维持摘要优先。
- 工具名/参数变更是否同步文档。

## 输出要求

- 给出工具矩阵变化（新增/变更/废弃）。
- 给出权限影响评估。
- 给出输出规模评估。
