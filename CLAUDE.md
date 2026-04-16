# Weboter 协作说明

## 项目目标

Weboter 当前阶段的目标是先交付一个可在 Linux/WSL 环境运行的 workflow service：

- 以 JSON workflow 作为唯一执行描述
- 允许用户手动上传单个 workflow 文件，或直接指定一个 workflow 目录
- 通过 CLI 触发解析、列举和执行
- 在不依赖 AI 介入的前提下稳定跑通基础自动化流程

MCP、AI 调试、目录自动监控和 GUI 仍是后续演进方向，但不应阻塞当前 service 闭环。

## 当前架构基线

项目按三层组织：

1. `weboter/public/`
   对外契约层，只放 Action、Control、IOPipe 和 workflow 数据模型。
2. `weboter/core/`
   核心执行层，负责 workflow 读取、builtin 注册、运行时上下文和执行器。
3. `weboter/builtin/`
   内置动作与控制。基础动作必须可独立加载；验证码等重依赖能力应保持可选。

## 开发约束

- 优先保持最小可运行闭环，不为了未来能力过早抽象。
- 新增能力默认先通过 CLI 暴露，再决定是否抽象成常驻 service 或 daemon。
- `weboter/core/engine/excutor.py` 是当前真实执行路径；旧的 `job.py`、`scheduler.py` 仍处于草稿态，不应作为新增功能入口。
- `builtin` 不应因为可选依赖缺失而整体不可导入。
- 文档、注释和说明使用中文。

## 近期优先级

1. 完善 workflow service 与 CLI 的目录/上传模式
2. 补齐 Linux/WSL 的安装、运行、验证文档
3. 为基础 workflow 补测试和示例
4. 再考虑目录监控、MCP 接口和 UI 配置能力