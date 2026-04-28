import json
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from weboter.app.config import AppConfig
from weboter.app.service import WorkflowService
from weboter.core.workflow_io import WorkflowReader


class WorkflowEditTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workflow_store = self.root / ".weboter" / "workflows"
        self.workflow_store.mkdir(parents=True, exist_ok=True)
        self.demo_path = self.workflow_store / "demo.json"
        self.demo_path.write_text(
            json.dumps(
                {
                    "id": "flow-demo",
                    "name": "demo",
                    "description": "",
                    "start_node_id": "n1",
                    "nodes": [
                        {
                            "id": "n1",
                            "name": "n1",
                            "description": "",
                            "action": "builtin.OpenPage",
                            "inputs": {},
                            "outputs": [],
                            "control": "builtin.NextNode",
                            "params": {"next_node": "n1"},
                            "log": "short",
                        }
                    ],
                    "sub_flows": [],
                    "log": "short",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        config = AppConfig(config_path=self.root / "weboter.yaml")
        config.paths.workspace_root = str(self.root)
        config.paths.data_root = ".weboter"
        config.paths.workflow_store = "workflows"
        config.paths.plugin_root = "plugins"

        with mock.patch("weboter.app.service.ensure_plugins_initialized"):
            self.service = WorkflowService(config=config)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_update_workflow_writes_flow_data(self):
        flow_payload = {
            "flow_id": "flow-demo",
            "name": "Demo Updated",
            "description": "updated",
            "start_node_id": "n2",
            "nodes": [
                {
                    "node_id": "n2",
                    "name": "Node Two",
                    "description": "desc",
                    "action": "builtin.OpenPage",
                    "inputs": {"url": "https://example.com"},
                    "outputs": [{"src": "page", "name": "page", "pos": "flow", "cvt": ""}],
                    "control": "builtin.NextNode",
                    "params": {"next_node": "n2"},
                    "log": "short",
                }
            ],
            "sub_flows": [],
            "log": "full",
        }

        saved_path = self.service.update_workflow(self.service.workflow_store, "demo", flow_payload)

        self.assertEqual(saved_path, self.demo_path)
        flow = WorkflowReader.from_json(self.demo_path)
        self.assertEqual(flow.name, "Demo Updated")
        self.assertEqual(flow.start_node_id, "n2")
        self.assertEqual(len(flow.nodes), 1)
        self.assertEqual(flow.nodes[0].node_id, "n2")
        self.assertEqual(flow.nodes[0].inputs["url"], "https://example.com")

    def test_update_workflow_rejects_duplicate_node_id(self):
        flow_payload = {
            "flow_id": "flow-demo",
            "name": "duplicate-test",
            "description": "",
            "start_node_id": "dup",
            "nodes": [
                {
                    "node_id": "dup",
                    "name": "A",
                    "description": "",
                    "action": "builtin.OpenPage",
                    "inputs": {},
                    "outputs": [],
                    "control": "builtin.NextNode",
                    "params": {},
                    "log": "short",
                },
                {
                    "node_id": "dup",
                    "name": "B",
                    "description": "",
                    "action": "builtin.OpenPage",
                    "inputs": {},
                    "outputs": [],
                    "control": "builtin.NextNode",
                    "params": {},
                    "log": "short",
                },
            ],
            "sub_flows": [],
            "log": "short",
        }

        with self.assertRaisesRegex(ValueError, "duplicate node_id"):
            self.service.update_workflow(self.service.workflow_store, "demo", flow_payload)
