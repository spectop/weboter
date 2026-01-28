"""
Docstring for weboter.role.action
This module defines the base class for actions within the Weboter role framework.

User defined actions should inherit from ActionBase and implement the execute method.
An action represents a specific operation that can be performed, such as clicking a button, submitting a form, or navigating to a different page.

Action should explicitly declare it's inputs and outputs, engine will create and manage the data flow between them (by role.IOBase).
"""

from abc import ABC, abstractmethod
from .interface import InputFieldDeclaration, OutputFieldDeclaration

class ActionBase(ABC):
    """Base class for actions within the Weboter role framework."""
    name: str = "BaseAction"
    description: str = "Base class for actions"
    inputs: list[InputFieldDeclaration] = []
    outputs: list[OutputFieldDeclaration] = []

    def __init__(self, name: str = "BaseAction"):
        self.name = name

    @abstractmethod
    async def execute(self, context: dict):
        """
        Execute the action with the given input and output.
        User defined actions must override this method.
        """
        raise NotImplementedError("Subclasses must implement this method.")