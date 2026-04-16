# Weboter 开发计划

## 当前评估

### 可复用部分

- `weboter/core/workflow_io.py` 已能把 JSON workflow 解析为 `Flow` / `Node` 模型
- `weboter/core/engine/excutor.py` 已具备真实的节点执行能力，是当前最可靠的执行入口
- `weboter/core/engine/runtime.py` 已实现变量上下文和节点输出切换
- `weboter/builtin/basic_action.py` 与 `weboter/builtin/basic_control.py` 已覆盖最基础的动作和控制能力

### 需要调整的部分

- `Engine`、`Job`、`Scheduler` 仍偏草稿态，暂不适合作为新增能力的承载层
- builtin 装配此前把验证码依赖当成硬依赖，影响基础 workflow 启动
- 项目此前缺少面向 Linux/WSL 的安装入口、CLI 和本地验证路径
- 文档仍停留在 PoC 阶段，没有体现当前的 service 目标

## 本阶段目标

先完成一个可用的 workflow service，重点是：

1. 用户可以手动上传单个 workflow 文件
2. 用户可以指定一个 workflow 目录进行解析和执行
3. 基础 workflow 可以在 Linux/WSL 环境稳定运行
4. 不依赖 `sgcc.json` 或任何敏感测试数据

## 已完成

1. 增加 CLI 入口：`weboter workflow --upload` / `weboter workflow --dir`
2. 增加 `WorkflowService`，承载上传、目录解析和执行逻辑
3. 增加 builtin 注册引导，避免 CLI 与执行器之间缺少装配
4. 让验证码能力退化为可选依赖，基础 workflow 不再被阻塞
5. 新增 `workflows/demo_empty.json` 作为本地最小验证样例
6. 移除 `workflows/sgcc.json`
7. 固定本地 service 数据目录语义，并为 CLI 增加稳定错误输出
8. 增加常驻后台 service 与 CLI client 调用链路
9. 将 service 传输层切换为 FastAPI/uvicorn，并补充机器可读的 JSON CLI 输出

## 下一阶段任务

1. 为 FastAPI service-client 与 `WorkflowService` 增加自动化测试
2. 设计 workflow 元数据接口，支持列举、查看和校验
3. 为后台 service 增加任务状态、执行历史和取消接口
4. 引入目录监听能力，支持后续自动监控模式
5. 在当前 service API 之上封装 MCP server，而不是让 MCP 解析 CLI 文本输出

## 验证基线

当前最小验证命令：

```bash
python -m weboter workflow --dir workflows --name demo_empty --execute
```

预期结果：

- CLI 能正确解析目录模式
- builtin 包自动注册成功
- `builtin.EmptyAction` 成功执行
- workflow 正常结束并输出 `executed:` 路径