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
        self._pw_inst : pw.Playwright = None
        self._browser : pw.Browser = None
        self._page : pw.Page = None

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
    def pw_inst(self) -> pw.Playwright:
        return self._pw_inst

    @pw_inst.setter
    def pw_inst(self, value: pw.Playwright):
        self._pw_inst = value

    @property
    def browser(self) -> pw.Browser:
        return self._browser
    
    @browser.setter
    def browser(self, value: pw.Browser):
        self._browser = value

    @property
    def page(self) -> pw.Page:
        return self._page
    
    @page.setter
    def page(self, value: pw.Page):
        self._page = value
    
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
