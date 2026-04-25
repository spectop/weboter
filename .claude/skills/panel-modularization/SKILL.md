---
name: panel-modularization
description: "处理 panel 页面结构、路由、静态资源拆分时必须使用。用户提到 /panel、assets、前端模块拆分、登录流异常时应触发。"
---

# Panel Modularization

## 目标

提升 panel 可维护性，并稳定前后端边界。

## 必做步骤

1. 先读取 `doc/interfaces/panel.md`。
2. 识别改动是页面结构、资源路径还是 API 交互。
3. 校验通配路由不会抢占 `/panel/api/*`。
4. 若涉及资源路径，校验打包配置。
5. 若需要后端配合字段，向 service agent 提交 Handoff Package。

## 重点检查

- `index.html` 是否保持壳层职责。
- 大脚本是否按模块职责拆分。
- 登录后关键 API（`/panel/api/me` 等）是否可达。

## 输出要求

- 说明路由层影响与资源层影响。
- 列出验证结果（登录、overview、plugins）。
- 标记文档同步状态。
