"""
Docstring for weboter.role.action
This module defines the base class for actions within the Weboter role framework.

User defined actions should inherit from ActionBase and implement the execute method.
An action represents a specific operation that can be performed, such as clicking a button, submitting a form, or navigating to a different page.

Action should explicitly declare it's inputs and outputs, engine will create and manage the data flow between them (by role.IOBase).
"""

from interface import InputDeclaration, OutputDeclaration

class ActionBase:
    """Base class for actions within the Weboter role framework."""

    description: str = "Base class for actions"
    inputs: InputDeclaration = None
    outputs: OutputDeclaration = None

    def __init__(self, name: str):
        self.name = name

    def execute(self, input, output):
        """
        Execute the action with the given input and output.
        User defined actions must override this method.
        :param input: a dict of input values
        :param output: a dict to store output values
        """
        raise NotImplementedError("Subclasses must implement this method.")