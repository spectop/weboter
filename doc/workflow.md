此文档介绍工作流的基本概念和结构。

# 概述

本项目中，使用 `json` 格式的配置文件来定义工作流。
工作流由若干个节点组成，每个节点表示工作流中的一个步骤。
节点之间通过有向边连接，表示步骤的执行顺序。

# 工作流结构

一个工作流配置文件通常包含以下几个部分：

- name: 工作流的名称
- description: 工作流的描述
- version: 该配置的版本
- nodes: 工作流中的节点列表

# 节点

一个节点表示一个执行步骤，节点包含以下内容

- id: 节点的唯一标识
- name: 节点名称，用于展示
- description: 节点描述，用于展示
- action: 该节点执行的动作
- input: 给 `action` 的输入
- control: 该节点的执行控制，一般多为 `builtin.NextNode` 表示无条件到下个节点
- params: 控制参数，给 `control` 的输入

一个节点，需要定义 `action` 和 `control` 中的至少一项。（仅 `control=builtin.NextNode` 无意义）
`control` 总是在 `action` 执行完成后被调用。

下面是对各项的详细介绍：

## action

动作表面该节点执行的具体操作。

本项目内置了一些常用动作，内置动作的包为 `builtin`.
如果使用内置动作，`action` 字段可以不填写包名
目前内置动作包括：

- `builtin.OpenPage`: 打开一个页面
- `builtin.ClickItem`: 点击页面上的某个元素

每个动作可能需要不同的输入，具体请参考各个动作的文档说明。

## input

**可选项**，表示给 `action` 的输入参数。
输入参数的格式和内容取决于具体的 `action`。
例如，对于 `builtin.OpenPage` 动作，输入参数为页面的 URL：

```json
{
  "url": "https://example.com"
}
```

输入参数可以是静态值，也可以通过变量引用动态生成。
动态生成的输入参数可以使用 `$var{param}` 语法引用工作流中的变量。

可用变量包括：

- `$env`: 环境变量
- `$prev`: 上一个节点的输出结果
- `$global`: 全局变量
- `$flow`: 工作流变量
- `$output`: 当前节点的输出结果（仅在 `control` 中可用）

> 在支持多工作流之前，`$flow` 变量与 `$global` 变量等价。

例如，引用环境变量 `USER`：

```json
{
  "username": "$env{USER}"
}
```

## control

表示该节点的执行控制逻辑。(默认值为 `builtin.NextNode`)
控制逻辑决定了节点执行完成后，工作流如何继续进行。

和 `action` 一样，`control` 也可以使用内置控制逻辑，包名为 `builtin`。
`control` 需要配合 `params` 字段使用，`params` 用于给 `control` 提供输入参数。

### builtin

#### NextNode

表示无条件跳转到下一个节点。

**Params**:

- next_node: **(required)** 下一个节点的 ID。如果不指定该参数


## params

表示给 `control` 的输入参数。
参数的格式和内容取决于具体的 `control`。

例如，对于 `builtin.NextNode` 控制逻辑，参数格式如下：

```json
{
  "next_node": "node_2"
}
```