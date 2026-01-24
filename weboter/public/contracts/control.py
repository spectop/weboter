from abc import ABC, abstractmethod
from interface import InputFieldDeclaration, OutputFieldDeclaration

class ControlBase(ABC):
    name: str = "BaseControl"
    description: str = "Base class for controls"
    inputs: list[InputFieldDeclaration] = []
    outputs: OutputFieldDeclaration = None # Commonly a single output of next node

    def __init__(self, name: str = "BaseControl"):
        self.name = name

    @abstractmethod
    async def calc_next(self, context: dict) -> str:
        """
        Determine the next node in the workflow based on the given context.
        User defined controls must override this method.
        """
        raise NotImplementedError("Subclasses must implement this method.")