from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class NodeOutputConfig:
    """Define how to store the output of a node"""
    src: str # must be same as the output field name declared in the action definition
    name: str = "" # The name to store in the data context, if empty, use src as the name
    pos: str = "flow" # where to store the output, accepted values: "flow", "global"
    cvt: str = "" # convert the output to a different type ["int", "float", "str", "bool"]

@dataclass
class Node:
    """表示工作流节点"""
    node_id: str  # 节点唯一标识
    name: str # name of the node
    description: str # description of the node
    action: str  # 格式: "package.ActionClass"
    inputs: Dict[str, str] = field(default_factory=dict)  # 输入参数
    outputs: List[NodeOutputConfig] = field(default_factory=list)  # # 输出参数，此处的 outputs 和 io.outputs 是不同的概念，io.outputs 是运行时的输出数据，而这里的 outputs 是节点定义中声明输出如何转储
    control: str = ""  # 流程控制 格式: "package.ControlClass"
    params: Dict[str, str] = field(default_factory=dict)  # 控制参数
    log: str = "short"  # log level for this node, accepted values: "none", "short", "full"

@dataclass
class Flow:
    """表示工作流定义"""
    flow_id: str  # 工作流唯一标识
    name: str # name of the node
    description: str # description of the node
    start_node_id: str = ""  # 起始节点ID，如果不指定，使用 __start__ 作为默认起始节点
    nodes: List[Node] = field(default_factory=list)  # 节点列表
    sub_flows: List['Flow'] = field(default_factory=list)  # 子工作流列表
    log: str = "short"  # log level for this flow, accepted values: "none", "short", "full"
