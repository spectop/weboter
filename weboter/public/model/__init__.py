"""Workflow data model components

Defines core data structures for workflow representation:
- Node: Workflow operation with action, control, inputs and outputs
- Link: Connection between workflow nodes
- DataContext: Runtime execution state
"""

from .model import Node, Flow

__all__ = ["Node", "Flow"]
