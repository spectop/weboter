---
name: core-contract-first
description: "处理 core/public/builtin 相关任务时强制使用：先审阅契约与接口文档，再改实现。用户提到 ActionBase、ControlBase、IOPipe、Flow/Node、插件装配时必须触发。"
---

# Core Contract First

## 目标

确保 Core 改动遵循“契约先行、实现后置”。

## 必做步骤

1. 先读取 `doc/interfaces/core.md`。
2. 若涉及插件注册或加载，额外读取 `doc/interfaces/plugin.md`。
3. 判断改动触及 `Stable` 还是 `Evolving` 边界。
4. 先更新接口文档，再改代码。
5. 若跨模块，按 `doc/interfaces/agent-collaboration.md` 输出 Handoff Package。

## 重点检查

- 是否修改了 `ActionBase` / `ControlBase` / `IOPipe` 签名。
- 是否引入跨层依赖（public 依赖 app/mcp）。
- 是否破坏插件仅依赖 contracts 的约束。

## 输出要求

- 明确列出接口影响范围。
- 给出兼容性结论（兼容 / 需迁移）。
- 标明是否同步更新 `doc/interfaces/core.md`。
