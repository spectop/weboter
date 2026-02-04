"""Core contracts for Weboter abstractions

Defines abstract base classes that all Weboter components must implement:
- ActionBase: Interface for automation actions
- ControlBase: Interface for flow control mechanisms
- Input/OutputFieldDeclaration: Schema definitions
"""

from .action import ActionBase
from .control import ControlBase
from .io_pipe import IOPipe
from .interface import InputFieldDeclaration, OutputFieldDeclaration
from .interface import LocatorDefine
from . import utils

__all__ = [
    "ActionBase",
    "ControlBase",
    "IOPipe",
    "InputFieldDeclaration",
    "OutputFieldDeclaration",
    "LocatorDefine",
    "utils"
]
