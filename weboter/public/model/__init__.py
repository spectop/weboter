"""Workflow data model components

Defines core data structures for workflow representation:
- NodeId: 节点 ID 引用的标记类型（str 子类）
- Node: Workflow operation with action, control, inputs and outputs
- Link: Connection between workflow nodes
- DataContext: Runtime execution state
"""

from .model import Node, Flow, NodeOutputConfig, NodeId

__all__ = ["Node", "Flow", "NodeOutputConfig", "NodeId"]
