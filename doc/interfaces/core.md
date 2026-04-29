# Core 对外接口文档

> 模块位置：`weboter/public/`、`weboter/core/`

## 1. 边界定义

Core 对外暴露两类接口：

- 契约层接口（Stable）
  - `ActionBase`
  - `ControlBase`
  - `IOPipe`
  - `InputFieldDeclaration` / `OutputFieldDeclaration`
  - `Node` / `Flow`
- 运行时装配接口（Evolving）
  - `ensure_builtin_packages_registered()`
  - `ensure_plugins_initialized()`
  - `refresh_plugins()`
  - `get_plugin_snapshot()`

## 2. 稳定契约（Stable）

### 2.1 Action 契约

文件：`weboter/public/contracts/action.py`

- 基类：`ActionBase`
- 必须实现：`async execute(io: IOPipe)`
- 类属性：`name`、`description`、`inputs`、`outputs`

约束：

- `execute` 必须是异步方法。
- `inputs`/`outputs` 字段声明必须与实际读写的 `io` 数据一致。

### 2.2 Control 契约

文件：`weboter/public/contracts/control.py`

- 基类：`ControlBase`
- 必须实现：`async calc_next(io: IOPipe) -> str`

约束：

- 返回值必须是下一节点 ID，或由上层定义的结束标识。

### 2.3 IOPipe 契约

文件：`weboter/public/contracts/io_pipe.py`

- 数据访问面：`inputs`、`outputs`、`params`
- 运行时上下文：`page`、`browser`、`executor`、`logger`
- 必须实现抽象属性：`cur_node`、`flow_data`

约束：

- 插件与 builtin 仅通过 IOPipe 读写运行时，不得直接依赖 Executor 内部结构。

### 2.4 模型契约

文件：`weboter/public/model/model.py`

- `Node`：节点定义
- `Flow`：工作流定义

约束：

- 工作流解析、执行、调试链路均应基于 `Flow/Node` 结构。

## 3. 装配接口（Evolving）

### 3.1 内置包注册

文件：`weboter/core/bootstrap.py`

- `ensure_builtin_packages_registered()`

语义：

- 保证 builtin action/control 包在 manager 中存在并可替换更新。

### 3.2 插件生命周期

文件：`weboter/core/plugin_loader.py`

- `ensure_plugins_initialized(config=None)`
- `refresh_plugins(config=None) -> dict`
- `get_plugin_snapshot(config=None) -> dict`

语义：

- 初始化时注册 builtin，并扫描目录插件 + 已安装插件。
- `refresh_plugins` 返回加载结果与错误摘要，供 Service/MCP/Panel 消费。

### 3.3 builtin 控制流能力（Evolving）

文件：`weboter/builtin/basic_control.py`

builtin 包提供通用控制流能力，默认至少包含：

- `NextNode`：无条件跳转到指定节点。
- `LoopUntil`：按变量值循环，支持最大重试次数与失败出口。
- `IfElse`：按比较条件在真分支与假分支间跳转。
- `ByMap`：按 key 从映射表选择下一节点，支持默认分支。
- `EndFlow`：直接结束当前流程（返回 `__end__`）。

约束：

- 新增 builtin control 必须保持 `ControlBase` 契约不变。
- 返回节点必须是合法节点 ID，或 `__end__` / `__exit__`。
- 不得引入对 `app/mcp` 层的依赖。

### 3.4 builtin 与重依赖能力边界（Evolving）

- builtin 适合保留轻量、稳定、强通用的 action/control。
- 涉及 OCR、视觉模型、机器学习推理等重依赖能力时，优先拆分为 plugin，而不是直接扩大 builtin 依赖集合。
- 若 builtin 已存在可选重依赖能力，新能力默认不继续沿用该模式扩张，除非它明显属于所有工作流都会复用的基础闭环。

## 4. 禁止跨层依赖

- `public` 禁止依赖 `core/app/mcp` 任何实现。
- 插件实现禁止直接依赖 `weboter.app.*`。
- `core` 对外只暴露契约和装配能力，不暴露内部执行细节对象。

## 5. 变更要求

下列变更必须先更新本文件：

- `ActionBase` / `ControlBase` / `IOPipe` 签名变更
- `Flow/Node` 字段语义变更
- 插件加载返回结构变更
