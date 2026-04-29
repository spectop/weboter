import asyncio
import types
import unittest
import sys


if "yaml" not in sys.modules:
    yaml_module = types.ModuleType("yaml")

    def _safe_load(_text):
        return {}

    yaml_module.safe_load = _safe_load
    sys.modules["yaml"] = yaml_module

if "playwright.async_api" not in sys.modules:
    async_api_module = types.ModuleType("playwright.async_api")

    class _StubPlaywright:
        pass

    class _StubBrowser:
        pass

    class _StubBrowserContext:
        pass

    class _StubPage:
        pass

    class _StubLocator:
        pass

    async_api_module.Playwright = _StubPlaywright
    async_api_module.Browser = _StubBrowser
    async_api_module.BrowserContext = _StubBrowserContext
    async_api_module.Page = _StubPage
    async_api_module.Locator = _StubLocator
    playwright_module = types.ModuleType("playwright")
    playwright_module.async_api = async_api_module
    sys.modules["playwright"] = playwright_module
    sys.modules["playwright.async_api"] = async_api_module

from weboter.builtin.basic_control import ByMap, EndFlow, IfElse, LoopUntil
from weboter.public.contracts.io_pipe import IOPipe


class _ControlIO(IOPipe):
    def __init__(self):
        super().__init__()
        self._cur_node = "node_a"
        self._flow_data = {}

    @property
    def cur_node(self) -> str:
        return self._cur_node

    @property
    def flow_data(self) -> dict:
        return self._flow_data

    @flow_data.setter
    def flow_data(self, value: dict):
        self._flow_data = value


class BuiltinControlsTests(unittest.TestCase):
    def test_ifelse_eq_true(self):
        io = _ControlIO()
        io.params["var"] = "ok"
        io.params["value"] = "ok"
        io.params["operator"] = "eq"
        io.params["then_node"] = "node_yes"
        io.params["else_node"] = "node_no"

        next_node = asyncio.run(IfElse().calc_next(io))
        self.assertEqual(next_node, "node_yes")

    def test_ifelse_gt_false(self):
        io = _ControlIO()
        io.params["var"] = 1
        io.params["value"] = 2
        io.params["operator"] = "gt"
        io.params["then_node"] = "node_yes"
        io.params["else_node"] = "node_no"

        next_node = asyncio.run(IfElse().calc_next(io))
        self.assertEqual(next_node, "node_no")

    def test_bymap_use_key_and_default(self):
        io = _ControlIO()
        io.params["key"] = "b"
        io.params["route_map"] = {"a": "node_a", "b": "node_b"}
        io.params["default_node"] = "node_default"
        self.assertEqual(asyncio.run(ByMap().calc_next(io)), "node_b")

        io.params["key"] = "x"
        self.assertEqual(asyncio.run(ByMap().calc_next(io)), "node_default")

    def test_endflow_returns_end(self):
        io = _ControlIO()
        next_node = asyncio.run(EndFlow().calc_next(io))
        self.assertEqual(next_node, "__end__")

    def test_loopuntil_with_try_limit_falls_back(self):
        io = _ControlIO()
        io.params["loop_back"] = "node_retry"
        io.params["loop_out"] = "node_done"
        io.params["var"] = False
        io.params["value"] = True
        io.params["loop_tries"] = 1
        io.params["loop_fail_node"] = "node_fail"

        next_node = asyncio.run(LoopUntil().calc_next(io))
        self.assertEqual(next_node, "node_fail")
