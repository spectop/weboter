"""
Module for Input/Output entities in Weboter.
"""

# todo: do we need this ?
class IOBase:
    """Base class for Input/Output entities."""

    description: str = "Base class for IO entities"

    def __init__(self, name: str, **kwargs) -> None:
        self.name = name

    def get(self):
        """Get the current value of the entity."""
        raise NotImplementedError("This method should be overridden by subclasses.")
    
    def set(self, value):
        """Set the value of the entity."""
        raise NotImplementedError("This method should be overridden by subclasses.")
    
    def convert(self, value):
        """Convert the given value to another format."""
        raise NotImplementedError("This method should be overridden by subclasses.")