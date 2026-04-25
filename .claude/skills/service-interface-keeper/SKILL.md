---
name: service-interface-keeper
description: "处理 service、router、CLI 对应 API 变更时必须使用。用户提到 HTTP 接口、WorkflowService、task/session/env、返回字段调整时应触发。"
---

# Service Interface Keeper

## 目标

保持 Service 对外接口稳定、可验证、可迁移。

## 必做步骤

1. 先读取 `doc/interfaces/service.md`。
2. 列出本次影响的路径、方法、字段。
3. 判断是否破坏 CLI/MCP 已有调用。
4. 先更新接口文档，再修改实现。
5. 若影响 panel/mcp，按 `doc/interfaces/agent-collaboration.md` 提供字段级 Handoff Package。

## 重点检查

- 是否新增/删除 HTTP 路由。
- 是否调整关键字段（如执行控制参数）。
- 是否放大默认返回窗口（违反保守默认）。

## 输出要求

- 变更清单包含路径 + 字段层影响。
- 给出兼容策略与回滚策略。
- 明确文档同步状态。
