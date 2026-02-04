"""
Contracts for Input/Output entities.
"""

from abc import ABC, abstractmethod
import playwright.async_api as pw

class IOPipe(ABC):
    
    def __init__(self):
        self._inputs = {}
        self._outputs = {}
        self._params = {}

    @property
    def inputs(self) -> dict:
        return self._inputs
    
    @property
    def outputs(self) -> dict:
        return self._outputs
    
    @outputs.setter
    def outputs(self, value):
        self._outputs = value
    
    @property
    def params(self) -> dict:
        return self._params

    @property
    @abstractmethod
    def cur_node(self) -> str:
        """Get the current node ID."""
        pass

    @property
    @abstractmethod
    def flow_data(self) -> dict:
        """Get the flow-level data storage."""
        pass

    @flow_data.setter
    @abstractmethod
    def flow_data(self, value: dict):
        pass
