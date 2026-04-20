import logging
import tempfile
import unittest
from pathlib import Path

from weboter.app.config import AppConfig, PathsConfig
from weboter.app.service import WorkflowService
from weboter.app.session import ExecutionSessionManager
from weboter.core.engine.excutor import Executor
from weboter.public.model import Flow, Node


class _FakeRuntime:
    def __init__(self):
        self.current_node_id = "node-1"
        self.data_context = type("DataContextStub", (), {"data": {"env": {"xxx": {"password": "secret123"}}}})()

    def get_value(self, key: str):
        if key == "$env{xxx.password}":
            return "secret123"
        return None


class _FakeExecutor:
    def __init__(self):
        self.runtime = _FakeRuntime()
        self.workflow = Flow(
            flow_id="flow-1",
            name="demo",
            description="",
            start_node_id="node-1",
            nodes=[Node(node_id="node-1", name="Node One", description="", action="", control="builtin.NextNode")],
        )


class ManagedEnvTests(unittest.TestCase):
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

    def test_service_env_supports_grouped_set_and_list(self):
        self.service.set_env("xxx.username", "alice")
        self.service.set_env("xxx.password", "secret123")

        result = self.service.list_env("xxx")

        self.assertEqual(result["group"], "xxx")
        self.assertEqual([item["name"] for item in result["items"]], ["xxx.password", "xxx.username"])
        self.assertEqual(result["items"][0]["masked_value"], "se***23")

    def test_service_env_get_is_masked_by_default(self):
        self.service.set_env("xxx.password", "secret123")

        masked = self.service.get_env("xxx.password")
        revealed = self.service.get_env("xxx.password", reveal=True)

        self.assertEqual(masked["value"], "se***23")
        self.assertTrue(masked["masked"])
        self.assertEqual(revealed["value"], "secret123")
        self.assertFalse(revealed["masked"])

    def test_service_env_tree_and_export_are_masked_by_default(self):
        self.service.set_env("xxx.username", "alice")
        self.service.set_env("xxx.password", "secret123")

        tree = self.service.env_tree()
        exported = self.service.export_env("xxx")

        self.assertEqual(tree["tree"]["item_count"], 2)
        self.assertEqual(tree["tree"]["children"][0]["name"], "xxx")
        self.assertTrue(exported["masked"])
        self.assertEqual(exported["data"]["username"], "al***ce")
        self.assertEqual(exported["data"]["password"], "se***23")

    def test_service_env_import_supports_merge_and_replace(self):
        self.service.import_env({"xxx": {"username": "alice"}})
        self.service.import_env({"xxx": {"password": "secret123"}})

        merged = self.service.export_env("xxx", reveal=True)
        self.assertEqual(merged["data"], {"username": "alice", "password": "secret123"})

        self.service.import_env({"mail": {"token": "abc"}}, replace=True)
        replaced = self.service.export_env(reveal=True)
        self.assertEqual(replaced["data"], {"mail": {"token": "abc"}})

    def test_executor_runtime_reads_managed_env(self):
        self.service.set_env("xxx.username", "alice")
        executor = Executor(managed_env=self.service.env_store.export_env_mapping())
        flow = Flow(
            flow_id="flow-1",
            name="demo",
            description="",
            start_node_id="node-1",
            nodes=[Node(node_id="node-1", name="Node One", description="", action="", control="builtin.NextNode")],
        )

        executor.load_workflow(flow)

        self.assertEqual(executor.runtime.get_value("$env{xxx.username}"), "alice")

    def test_session_runtime_masks_env_values(self):
        manager = ExecutionSessionManager(self.root / "sessions", logging.getLogger("test.env.session"))
        session = manager.create_session(
            task_id="task-1",
            workflow_path=self.root / "demo.json",
            workflow_name="demo",
            log_path=self.root / "task.log",
        )
        session._active_executor = _FakeExecutor()

        result = session.describe_runtime_value("$env{xxx.password}")
        preview = session._serialize_runtime_preview({"env": {"xxx": {"password": "secret123"}}})

        self.assertEqual(result["value"], "se***23")
        self.assertEqual(preview["items"]["env"]["masked"], True)
