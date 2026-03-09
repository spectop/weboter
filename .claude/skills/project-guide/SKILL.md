---
name: project-guide
description: "Weboter 项目指导 - Python 工作流自动化框架，用于浏览器自动化交互。工作流通过 JSON 文件配置，包含动作和控制节点，实现可配置的网页自动化任务。"
model: inherit
color: green
---

# Weboter 项目指导

## 项目概览

Weboter 是一个 Python 工作流自动化框架，专门用于浏览器交互自动化。它通过 JSON 配置文件定义工作流，避免了频繁修改代码的需求。框架采用类似 ComfyUI 的配置格式，支持多种节点类型和参数设置，便于后续的可视化界面拓展。

### 项目目标

1. **配置驱动的自动化**：通过 JSON 配置文件定义复杂工作流，无需修改代码
2. **模块化设计**：支持自定义动作（Action）和控制（Control）扩展
3. **AI 集成**：为 AI 辅助调试和错误恢复提供接口
4. **可视化支持**：为后续 GUI 界面提供基础架构

### 架构分层

框架采用三层架构设计：

1. **公共层（Public）**：定义抽象基类和接口，是外部包的唯一依赖
2. **核心层（Core）**：实现引擎、运行时管理、工作流执行
3. **内置实现（Builtin）**：提供常用动作和控制的默认实现

## 核心组件

### 工作流定义

工作流由节点（Node）组成，每个节点包含：
- **Action**：具体执行的操作（如点击、输入）
- **Control**：节点执行后的流向控制
- **Inputs/Params**：动作和控制的输入参数

### 变量系统

支持多种变量类型：
- `$env{...}`：环境变量
- `$global{...}`：全局变量
- `$flow{...}`：工作流变量
- `$prev{...}`：前一个节点的输出
- `$output{...}`：当前节点的输出（仅限 Control 使用）

### 执行引擎

- **Job**：封装单个工作流执行
- **Runtime**：提供执行上下文
- **Scheduler**：管理工作流调度
- **Executor**：执行工作流节点

## 接口与扩展

### Action 扩展
自定义动作需继承 `ActionBase`，实现 `execute()` 方法，并声明输入输出字段。

### Control 扩展  
自定义控制需继承 `ControlBase`，实现 `calc_next()` 方法，决定下一节点。

### 包管理器
- `ActionManager`：动作包注册、更新、卸载
- `ControlManager`：控制包注册、更新、卸载

## 后续开发计划

### MCP/AI Guard（暂未实现）
- **目标**：提供 MCP 功能给 AI 调用，自动化执行出错时，AI 可以介入
- **功能**：
  - 根据提供的错误信息，修改工作流配置
  - 应对网址页面结构变化
  - 智能错误恢复策略

### UI Config（暂未实现）
- **目标**：可视化界面配置工作流
- **功能**：
  - 节点拖拽式编辑
  - 实时参数配置
  - 工作流可视化预览

### AI Config（暂未实现）
- **目标**：AI 通过 MCP 及相关暴露能力，调试、创建、保存工作流
- **功能**：
  - AI 辅助工作流生成
  - 智能参数优化
  - 错误诊断和修复建议

## 关键文件参考

### 配置文档
- `workflows/*.json` - 工作流配置文件
- `doc/workflow.md` - 工作流配置规范

### 核心架构
- `weboter/public/contracts/` - 抽象基类和接口
- `weboter/core/engine/` - 核心执行引擎
- `weboter/builtin/` - 内置动作和控制

## 使用指导

### 快速开始
1. 创建 JSON 工作流文件
2. 使用内置动作：`builtin.OpenPage`、`builtin.ClickItem` 等
3. 运行工作流执行引擎

### 自定义扩展
1. 创建新的 Action 或 Control 类
2. 注册到包管理器
3. 在工作流中引用 `package.ClassName`

---

## Reference

### 详细模块信息（按需参考）

#### 公共契约层
**位置**: `weboter/public/contracts/`

1. **ActionBase** (`action.py`)
   - 所有动作的抽象基类
   - 定义 `execute()` 方法和输入输出字段声明
   - 工作流执行时的核心接口

2. **ControlBase** (`control.py`)
   - 所有控制的抽象基类
   - 定义 `calc_next()` 方法
   - 决定节点执行后的流向

3. **IOBase** (`io_pipe.py`)
   - 输入输出处理的抽象基类
   - 管理动作和控制之间的数据流

4. **接口定义** (`interface.py`)
   - `InputFieldDeclaration`：输入字段声明
   - `OutputFieldDeclaration`：输出字段声明
   - 类型安全的字段定义

#### 数据模型层
**位置**: `weboter/public/model/`

1. **Node** (`model.py`)
   - 工作流节点模型
   - 包含 action、control、inputs、outputs 等属性
   - 工作流执行的基本单元

2. **Flow** (`model.py`)
   - 工作流整体模型
   - 包含节点集合和起始节点

#### 核心引擎层
**位置**: `weboter/core/engine/`

1. **ActionManager** (`action_manager.py`)
   - 动作包管理器
   - 支持包注册、替换、卸载
   - 强类型容器管理

2. **ControlManager** (`control_manager.py`)
   - 控制包管理器
   - 与 ActionManager 类似功能
   - 统一的管理接口

3. **Runtime** (`runtime.py`)
   - 执行上下文管理器
   - 维护数据上下文（DataContext）
   - 管理当前节点状态

4. **Job** (`job.py`)
   - 单个工作流执行封装
   - 生命周期管理

5. **Scheduler** (`scheduler.py`)
   - 工作流调度器
   - （当前为占位实现）

6. **Executor** (`excutor.py`)
   - 节点执行器
   - （当前为占位实现）

#### 内置实现
**位置**: `weboter/builtin/`

1. **基本动作** (`basic_action.py`)
   - `OpenBrowser`：打开浏览器
   - `OpenPage`：打开页面
   - `ClickItem`：点击元素
   - `FillInput`：填充输入框
   - `WaitElement`：等待元素
   - `SleepFor`：延时等待

2. **验证码动作** (`captcha_action.py`)
   - `SimpleSlideCaptcha`：简单滑块验证码
   - `SimpleSlideNCC`：基于 NCC 的滑块验证码

3. **基本控制** (`basic_control.py`)
   - `NextNode`：无条件跳转到下一节点
   - `LoopUntil`：循环直到条件满足

#### 辅助工具
**位置**: `weboter/core/`

1. **Workflow IO** (`workflow_io.py`)
   - 工作流文件读写
   - JSON 解析和验证

### 开发约定

#### 命名规范
- 动作和控制使用点分隔名：`package.ClassName`
- 内置包名固定为 `"builtin"`
- 自定义包名应唯一且有意义

#### 包管理操作
```python
# 注册新包
action_manager.register_package("custom", [CustomAction])
control_manager.register_package("custom", [CustomControl])

# 更新现有包
action_manager.replace_package("builtin", new_actions)

# 卸载包
action_manager.unregister_package("deprecated")
```

#### 文件组织
- `workflows/` - 工作流配置文件
- `doc/` - 项目文档
- `weboter/` - 源代码
  - `public/` - 公共接口
  - `core/` - 核心实现
  - `builtin/` - 内置组件

### 常用命令

#### 环境设置
```bash
# 虚拟环境
python -m venv .venv
.\.venv\Scripts\activate

# 依赖安装
pip install -r requirements.txt
```

#### 测试运行
```bash
# 运行测试工作流
python -m weboter.core.workflow_io workflows/example.json
```

### 错误处理建议

1. **动作执行失败**：检查输入参数和环境条件
2. **控制逻辑异常**：验证下一节点ID存在性
3. **变量解析错误**：检查变量格式和数据存在性
4. **包注册冲突**：确保包名唯一性

### AI 集成点

当前支持 AI 介入的能力：
- 工作流生成（基于模板）
- 参数化配置优化
- 执行状态监控

未来计划：
- 运行时错误诊断
- 智能配置修复
- 自适应工作流调整