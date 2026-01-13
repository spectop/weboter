from dataclasses import dataclass

@dataclass
class IOInterface:
    """Define an interface for input/output"""
    name: str
    description: str = "Interface for IO entities"
    type: str = "Any" # Type can be specified as needed

@dataclass
class InputDeclaration(IOInterface):
    """Define an input declaration"""
    required: bool = True
    fields: list[IOInterface] = None

@dataclass
class OutputDeclaration(IOInterface):
    """Define an output declaration"""
    fields: list[IOInterface] = None