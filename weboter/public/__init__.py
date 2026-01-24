"""Public API package for Weboter framework

This package defines interfaces and models that describe the Weboter automation framework
public API. All implementations must adhere to these contracts.

Modules:
- contracts: Abstract base classes for actions, controls, and I/O
- model: Workflow data models for nodes, links, and execution context
"""

# Re-exports for top-level imports
from .contracts import ActionBase, ControlBase, IOBase
from .model import Node, Link
