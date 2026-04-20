import tempfile
import unittest
from pathlib import Path

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
