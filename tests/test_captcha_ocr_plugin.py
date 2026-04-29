import tempfile
import types
import unittest
from pathlib import Path
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

from weboter.app.config import AppConfig, PathsConfig
from weboter.app.service import WorkflowService


class CaptchaOcrPluginTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.plugins_root = self.root / "plugins"
        self.plugins_root.mkdir(parents=True, exist_ok=True)

        source_root = Path(__file__).resolve().parent.parent
        plugin_src = source_root / "plugins" / "captcha_ocr"
        plugin_dst = self.plugins_root / "captcha_ocr"
        plugin_dst.mkdir(parents=True, exist_ok=True)
        plugin_dst.joinpath("__init__.py").write_text(plugin_src.joinpath("__init__.py").read_text(encoding="utf-8"), encoding="utf-8")

        self.config = AppConfig(
            paths=PathsConfig(
                workspace_root=str(self.root),
                data_root=".weboter",
                workflow_store="workflows",
                plugin_root="plugins",
            )
        )
        self.service = WorkflowService(config=self.config)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_captcha_ocr_actions_visible_after_refresh(self):
        refreshed = self.service.refresh_plugins()
        self.assertGreaterEqual(refreshed["loaded_count"], 1)

        items = self.service.list_actions()["items"]
        full_names = {item["full_name"] for item in items}

        self.assertIn("captcha_ocr.OcrReadText", full_names)
        self.assertIn("captcha_ocr.ClickTextOrderCaptcha", full_names)