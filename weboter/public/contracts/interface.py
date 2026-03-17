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
    # Position of the element if multiple are found, accepted values: "first", "last", "all", or an integer index (0-based)
    pos: str | int = "first"
    sub: 'LocatorDefine | None' = None  # Optional sub-locator for nested elements

    def to_dict(self) -> dict:
        return {
            "element": self.element,
            "type": self.type,
            "ext": self.ext,
            "pos": self.pos
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LocatorDefine':
        return cls(
            element=data.get("element", ""),
            type=data.get("type", "text"),
            ext=data.get("ext", {}),
            pos=data.get("pos", "first")
        )
    
    def to_list(self) -> list:
        """Convert to a list format for serialization, with sub locators as nested lists"""
        result = [self.to_dict()]
        if self.sub:
            result.append(self.sub.to_list())
        return result
    
    @classmethod
    def from_list(cls, data: list) -> 'LocatorDefine':
        """
        data[0] is the main locator, data[1:] are sub locators
        """
        if not data or not isinstance(data, list):
            raise ValueError("Input data must be a non-empty list")
        inst = cls.from_dict(data[0])
        inst.sub = cls.from_list(data[1:]) if len(data) > 1 else None
        return inst
    
    def serialize(self) -> str:
        return self.to_list() if self.sub else self.to_dict()

    @classmethod
    def deserialize(cls, data: dict | list) -> 'LocatorDefine':
        if isinstance(data, list):
            return cls.from_list(data)
        elif isinstance(data, dict):
            return cls.from_dict(data)
        else:
            raise ValueError("Input data must be a dict or a list")

@dataclass
class VarPicker:
    """
    A variable picker defines how to pick a variable from the data context, which can be used in action inputs or control parameters.
    """
    name: str
    src: str  # Source of the variable
    dst: str = ""  # Destination variable name to store the picked value
    value: any = None  # Value of the variable

    def serialize(self) -> dict:
        return {
            "name": self.name,
            "src": self.src,
            "dst": self.dst,
            "value": self.value
        }

    @classmethod
    def deserialize(cls, data: dict) -> 'VarPicker':
        return cls(
            name=data.get("name", ""),
            src=data.get("src", ""),
            dst=data.get("dst", ""),
            value=data.get("value", None)
        )