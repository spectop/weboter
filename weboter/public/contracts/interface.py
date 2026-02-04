from dataclasses import dataclass, field

@dataclass
class InputFieldDeclaration:
    """Define an input field declaration"""
    name: str
    description: str = "Input field"
    required: bool = True # Is this field must be provided
    accepted_types: list = field(default_factory=lambda: ["str"]) # Accepted data types
    default: any = None # Default value if not provided

@dataclass
class OutputFieldDeclaration:
    """Define an output field declaration"""
    name: str
    description: str = "Output field"
    type: str = "any" # Data type of the field


@dataclass
class LocatorDefine:
    """Define a locator declaration"""
    element: str
    type: str = "text"  # Type of the locator (role, text, label, placeholder, alt, title, testid, css, xpath)
    ext: dict = field(default_factory=dict)  # Additional locator information

    def to_dict(self) -> dict:
        return {
            "element": self.element,
            "type": self.type,
            "ext": self.ext
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LocatorDefine':
        return cls(
            element=data.get("element", ""),
            type=data.get("type", "text"),
            ext=data.get("ext", {})
        )