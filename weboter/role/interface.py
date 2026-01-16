from dataclasses import dataclass

@dataclass
class InputFieldDeclaration:
    """Define an input field declaration"""
    name: str
    description: str = "Input field"
    required: bool = True # Is this field must be provided
    accepted_types: list[str] = [] # List of accepted data types
    default: any = None # Default value if not provided

@dataclass
class OutputFieldDeclaration:
    """Define an output field declaration"""
    name: str
    description: str = "Output field"
    type: str = "any" # Data type of the field
