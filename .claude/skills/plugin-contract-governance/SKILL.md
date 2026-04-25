---
name: plugin-contract-governance
description: "处理插件开发、插件加载、插件发布、zip 上传规则、catalog 变更时必须使用。用户提到 plugin_root、entry point、package_name/actions/controls 时应触发。"
---

# Plugin Contract Governance

## 目标

保证插件生态扩展能力与主系统兼容。

## 必做步骤

1. 先读取 `doc/interfaces/plugin.md`。
2. 若涉及 contracts，额外读取 `doc/interfaces/core.md`。
3. 校验加载失败隔离与错误摘要输出。
4. 先更新接口文档，再改插件加载或上传逻辑。
5. 若 catalog 字段变化，向 service/mcp 提交 Handoff Package。

## 重点检查

- 插件导出字段是否完整。
- 目录插件与安装插件发现是否仍兼容。
- zip 上传是否满足结构和路径安全校验。

## 输出要求

- 描述契约影响（导出字段/发现机制/刷新返回）。
- 给出兼容性结论。
- 标记文档同步状态。
