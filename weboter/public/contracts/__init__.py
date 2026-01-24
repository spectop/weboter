"""Core contracts for Weboter abstractions

Defines abstract base classes that all Weboter components must implement:
- ActionBase: Interface for automation actions
- ControlBase: Interface for flow control mechanisms
- IOBase: Interface for input/output handling
- Input/OutputFieldDeclaration: Schema definitions
"""

from .action import ActionBase
from .control import ControlBase
from .io import IOBase
from .interface import InputFieldDeclaration, OutputFieldDeclaration

__all__ = [
    "ActionBase",
    "ControlBase",
    "IOBase",
    "InputFieldDeclaration",
    "OutputFieldDeclaration"
]
