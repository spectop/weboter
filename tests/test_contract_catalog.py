import tempfile
import types
import unittest
from pathlib import Path
import sys
from unittest import mock


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

from weboter.app.config import AppConfig, PathsConfig
from weboter.app.service import WorkflowService


class ContractCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config = AppConfig(
            paths=PathsConfig(
                workspace_root=str(self.root),
                data_root=".weboter",
                workflow_store="workflows",
            )
        )
        self.service = WorkflowService(config=self.config)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_actions_returns_summary_only(self):
        result = self.service.list_actions()

        self.assertIn("items", result)
        self.assertTrue(any(item["full_name"] == "builtin.OpenPage" for item in result["items"]))
        open_page = next(item for item in result["items"] if item["full_name"] == "builtin.OpenPage")
        self.assertIn("input_count", open_page)
        self.assertNotIn("inputs", open_page)

    def test_get_action_returns_full_contract(self):
        result = self.service.get_action("builtin.OpenPage")

        self.assertIsNotNone(result)
        action = result["action"]
        self.assertEqual(action["full_name"], "builtin.OpenPage")
        self.assertIn("inputs", action)
        self.assertGreaterEqual(len(action["inputs"]), 1)

    def test_get_control_returns_full_contract(self):
        result = self.service.get_control("builtin.NextNode")

        self.assertIsNotNone(result)
        control = result["control"]
        self.assertEqual(control["full_name"], "builtin.NextNode")
        self.assertIn("inputs", control)
        self.assertIn("outputs", control)

    def test_captcha_actions_are_visible_in_catalog(self):
        result = self.service.list_actions()

        full_names = {item["full_name"] for item in result["items"]}
        self.assertIn("builtin.SimpleSlideCaptcha", full_names)
        self.assertIn("builtin.SimpleSlideNCC", full_names)

    def test_refresh_plugins_loads_plugin_from_plugin_root(self):
        plugin_dir = self.root / "plugins" / "demo_plugin"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        plugin_dir.joinpath("__init__.py").write_text(
            "\n".join(
                [
                    "from weboter.public.contracts.action import ActionBase",
                    "from weboter.public.contracts.io_pipe import IOPipe",
                    "",
                    "package_name = \"demo\"",
                    "",
                    "class DemoAction(ActionBase):",
                    "    name = \"DemoAction\"",
                    "    description = \"demo action\"",
                    "    inputs = []",
                    "    outputs = []",
                    "",
                    "    async def execute(self, io: IOPipe):",
                    "        return None",
                    "",
                    "actions = [DemoAction]",
                    "controls = []",
                ]
            ),
            encoding="utf-8",
        )

        before = {item["full_name"] for item in self.service.list_actions()["items"]}
        self.assertNotIn("demo.DemoAction", before)

        refreshed = self.service.refresh_plugins()
        self.assertGreaterEqual(refreshed["loaded_count"], 1)

        after = {item["full_name"] for item in self.service.list_actions()["items"]}
        self.assertIn("demo.DemoAction", after)

    def test_refresh_plugins_loads_installed_weboter_distribution(self):
        module_name = "weboter_http_plugin"
        module = types.ModuleType(module_name)

        from weboter.public.contracts.action import ActionBase
        from weboter.public.contracts.io_pipe import IOPipe

        class HttpPing(ActionBase):
            name = "HttpPing"
            description = "http ping"
            inputs = []
            outputs = []

            async def execute(self, io: IOPipe):
                return None

        module.package_name = "weboter_http"
        module.actions = [HttpPing]
        module.controls = []
        sys.modules[module_name] = module

        class _FakeDist:
            metadata = {"Name": "weboter-http"}

            def read_text(self, name: str):
                if name == "top_level.txt":
                    return module_name + "\n"
                return ""

        try:
            with mock.patch("weboter.core.plugin_loader.metadata.distributions", return_value=[_FakeDist()]):
                refreshed = self.service.refresh_plugins()

            self.assertGreaterEqual(refreshed["loaded_count"], 1)
            names = {item["full_name"] for item in self.service.list_actions()["items"]}
            self.assertIn("weboter_http.HttpPing", names)
        finally:
            sys.modules.pop(module_name, None)
