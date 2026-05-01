import asyncio
import sys
import types
import unittest


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

from weboter.builtin.basic_action import SetData
from weboter.core.engine.runtime import DataContext
from weboter.public.contracts.io_pipe import IOPipe


class _FakeRuntime:
    def __init__(self):
        self.ctx = DataContext()

    def set_value(self, key: str, value):
        self.ctx.set_data(key, value)

    def get_value(self, key: str):
        return self.ctx.get_data(key)


class _FakeExecutor:
    def __init__(self):
        self.runtime = _FakeRuntime()


class _ActionIO(IOPipe):
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


class SetDataActionTests(unittest.TestCase):
    def test_setdata_can_write_multiple_scopes_and_types(self):
        io = _ActionIO()
        io.executor = _FakeExecutor()
        action = SetData()

        cases = [
            ("$flow{user.profile}", {"name": "alice", "age": 20}),
            ("$global{flags.enabled}", True),
            ("$env{sgcc.phone}", "13800000000"),
            ("$prev_outputs{json.items}", [1, 2, 3]),
            ("$cur_outputs{score}", 0.98),
        ]

        for key, value in cases:
            io.inputs.clear()
            io.outputs.clear()
            io.inputs.update({"key": key, "value": value})
            asyncio.run(action.execute(io))
            self.assertEqual(io.executor.runtime.get_value(key), value)
            self.assertEqual(io.outputs["key"], key)
            self.assertEqual(io.outputs["value"], value)

    def test_setdata_rejects_invalid_key(self):
        io = _ActionIO()
        io.executor = _FakeExecutor()
        io.inputs.update({"key": "flow.user", "value": 1})

        with self.assertRaisesRegex(ValueError, "variable reference"):
            asyncio.run(SetData().execute(io))

    def test_setdata_requires_runtime(self):
        io = _ActionIO()
        io.inputs.update({"key": "$flow{a}", "value": 1})

        with self.assertRaisesRegex(ValueError, "Executor runtime"):
            asyncio.run(SetData().execute(io))
