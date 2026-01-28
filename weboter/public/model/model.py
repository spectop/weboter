from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class Node:
    """表示工作流节点"""
    node_id: str  # 节点唯一标识
    name: str # name of the node
    description: str # description of the node
    action: str  # 格式: "package.ActionClass"
    inputs: Dict[str, str] = field(default_factory=dict)  # 输入参数
    control: str = ""  # 流程控制 格式: "package.ControlClass"
    params: Dict[str, str] = field(default_factory=dict)  # 控制参数

@dataclass
class Flow:
    """表示工作流定义"""
    flow_id: str  # 工作流唯一标识
    name: str # name of the node
    description: str # description of the node
    start_node_id: str = ""  # 起始节点ID
    nodes: List[Node] = field(default_factory=list)  # 节点列表
