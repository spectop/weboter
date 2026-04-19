import asyncio
import logging
import sys
import tempfile
from pathlib import Path
import types
import unittest
from unittest import mock


if "playwright.async_api" not in sys.modules:
    async_api_module = types.ModuleType("playwright.async_api")

    class _StubPage:
        pass

    async_api_module.Page = _StubPage
    playwright_module = types.ModuleType("playwright")
    playwright_module.async_api = async_api_module
    sys.modules["playwright"] = playwright_module
    sys.modules["playwright.async_api"] = async_api_module

from weboter.app import session as session_module
from weboter.app.session import ExecutionSessionManager, SESSION_STATUS_PAUSED
from weboter.public.model import Flow, Node


class _FakeDataContext:
    def __init__(self):
        self.data = {"flow": {"value": 1}}


class _FakeRuntime:
    def __init__(self, node: Node, page=None):
        self.current_node_id = node.node_id
        self.data_context = _FakeDataContext()
        self.nodes = {node.node_id: node}
        self._values = {"$flow{form}": {"name": "alice", "roles": ["admin", "operator"]}}
        if page is not None:
            self._values["$global{{current_page}}"] = page

    def get_node_name(self, node_id: str):
        return self.nodes[node_id].name

    def get_value(self, key: str):
        return self._values.get(key)

    def set_value(self, key: str, value):
        self._values[key] = value

    def set_current_node(self, node_id: str):
        self.current_node_id = node_id


class _FakeExecutor:
    def __init__(self, flow: Flow, node: Node, page=None):
        self.workflow = flow
        self.runtime = _FakeRuntime(node, page=page)


class _FakePage:
    def __init__(self):
        self.url = "about:blank"

    async def title(self):
        return "Fake Page"

    async def goto(self, url: str):
        self.url = url

    async def content(self):
        return "<html><body>fake</body></html>"

    async def screenshot(self, path: str, full_page: bool = True):
        Path(path).write_bytes(b"fake")


class SessionDebugTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.logger = logging.getLogger(f"test.session.{id(self)}")
        self.logger.handlers.clear()
        self.manager = ExecutionSessionManager(self.root, self.logger)
        self.node = Node(
            node_id="node-1",
            name="Node One",
            description="",
            action="builtin.Noop",
            control="builtin.NextNode",
        )
        self.flow = Flow(
            flow_id="flow-1",
            name="demo",
            description="",
            start_node_id="node-1",
            nodes=[self.node],
        )
        self.session = self.manager.create_session(
            task_id="task-1",
            workflow_path=self.root / "demo.json",
            workflow_name="demo",
            log_path=self.root / "task.log",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    async def test_breakpoint_pauses_before_step(self):
        self.session.configure_breakpoints([
            {"id": "bp-1", "phase": "before_step", "node_id": "node-1", "once": True}
        ])
        executor = _FakeExecutor(self.flow, self.node)

        task = asyncio.create_task(self.session.before_step(executor, self.node))
        await asyncio.sleep(0.2)

        self.assertEqual(self.session.record.status, SESSION_STATUS_PAUSED)
        self.assertEqual(self.session.record.pause_reason, "breakpoint")
        self.assertEqual(self.session.record.last_stop["node_id"], "node-1")
        self.assertEqual(self.session.record.breakpoints, [])

        await asyncio.to_thread(self.manager.resume, self.session.record.session_id)
        await task

    async def test_session_created_with_pause_before_start_stops_before_first_node(self):
        session = self.manager.create_session(
            task_id="task-2",
            workflow_path=self.root / "demo.json",
            workflow_name="demo",
            log_path=self.root / "task-2.log",
            pause_before_start=True,
        )
        executor = _FakeExecutor(self.flow, self.node)

        task = asyncio.create_task(session.before_step(executor, self.node))
        await asyncio.sleep(0.2)

        self.assertEqual(session.record.status, SESSION_STATUS_PAUSED)
        self.assertEqual(session.record.pause_reason, "interrupt")
        self.assertEqual(session.record.last_stop["reason"], "start_before_first_node")

        await asyncio.to_thread(self.manager.resume, session.record.session_id)
        await task

    async def test_page_script_runs_with_guarded_context(self):
        page = _FakePage()
        executor = _FakeExecutor(self.flow, self.node, page=page)

        with mock.patch.object(session_module.pw, "Page", _FakePage):
            result = await self.session._run_page_script(
                executor,
                "await page.goto('https://example.com')\nreturn {'url': page.url, 'arg': context['arg']}",
                arg={"mode": "debug"},
                timeout_ms=1000,
            )

        self.assertEqual(result["result"]["type"], "dict")
        self.assertEqual(result["result"]["items"]["url"], "https://example.com")
        self.assertEqual(result["result"]["items"]["arg"]["type"], "dict")
        self.assertEqual(result["snapshot"]["phase"], "page_script")
        self.assertTrue(Path(result["page"]["html_path"]).is_file())
        self.assertTrue(Path(result["page"]["screenshot_path"]).is_file())

    async def test_page_script_rejects_import(self):
        with self.assertRaisesRegex(ValueError, "Import"):
            self.session._compile_page_script("import os\nreturn 1")

    async def test_snapshot_list_returns_summary_only(self):
        executor = _FakeExecutor(self.flow, self.node)
        await self.session.capture_snapshot(executor, phase="before_step", node=self.node)

        items = self.manager.get_snapshots(self.session.record.session_id, limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["phase"], "before_step")
        self.assertIn("available_sections", items[0])
        self.assertNotIn("runtime", items[0])
        self.assertNotIn("workflow", items[0])

    async def test_snapshot_detail_returns_requested_sections_only(self):
        executor = _FakeExecutor(self.flow, self.node)
        await self.session.capture_snapshot(executor, phase="before_step", node=self.node)

        detail = self.manager.get_snapshot_detail(
            self.session.record.session_id,
            1,
            sections=["runtime", "node"],
        )

        self.assertIn("sections", detail)
        self.assertEqual(set(detail["sections"].keys()), {"runtime", "node"})
        self.assertNotIn("workflow", detail["sections"])

    async def test_workflow_summary_and_node_detail_are_split(self):
        executor = _FakeExecutor(self.flow, self.node)
        self.session._active_executor = executor

        summary = self.session.describe_workflow()
        detail = self.session.describe_workflow_node("node-1")

        self.assertEqual(summary["workflow"]["node_count"], 1)
        self.assertEqual(summary["workflow"]["nodes"][0]["node_id"], "node-1")
        self.assertNotIn("inputs", summary["workflow"]["nodes"][0])
        self.assertEqual(detail["node"]["node_id"], "node-1")
        self.assertIn("inputs", detail["node"])

    async def test_runtime_value_returns_preview(self):
        executor = _FakeExecutor(self.flow, self.node)
        self.session._active_executor = executor

        result = self.session.describe_runtime_value("$flow{form}")

        self.assertEqual(result["key"], "$flow{form}")
        self.assertEqual(result["value"]["type"], "dict")
        self.assertIn("items", result["value"])