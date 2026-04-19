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
- 任何代码修改完成后，都要主动判断这次改动是否需要重新打包 wheel；如果需要，则由 agent 自行执行版本升级与打包，不再等待用户额外提醒。
- 每次重新打包后，都必须明确告知用户新的 wheel 文件名；如果文件名发生变化，也必须显式说明新旧文件名差异。

### MCP 输出约束

- 任何新增或修改的 MCP 工具，都必须默认避免返回巨量上下文。
- MCP 接口优先采用“摘要 + 按需详情”的渐进式披露设计：先返回可获取能力、摘要、索引或 key，再由 agent 按节点、section、path 或分页参数继续拉取。
- 不要默认返回完整 workflow、完整 runtime、完整页面内容、超长日志或大列表；这些内容必须拆成 detail 接口、分页接口或受限窗口。
- 日志类和列表类工具必须设置保守默认值，并在 MCP 层做上限限制；需要更多内容时，由 agent 显式追加参数再次请求。
- 如果某个工具仍可能返回较大结果，返回体中必须明确下一步可用的 detail 方法、section、索引或 key，让 agent 知道如何继续获取，而不是一次性把全部正文发回。

## 近期优先级

1. 完善 workflow service 与 CLI 的目录/上传模式
2. 补齐 Linux/WSL 的安装、运行、验证文档
3. 为基础 workflow 补测试和示例
4. 再考虑目录监控、MCP 接口和 UI 配置能力