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

    def switch_outputs(self):
        current = self._values.get("$cur_outputs{result}")
        if current is not None:
            self._values["$prev_outputs{result}"] = current
            self._values["$cur_outputs{result}"] = None


class _FakeExecutor:
    def __init__(self, flow: Flow, node: Node, page=None):
        self.workflow = flow
        self.runtime = _FakeRuntime(node, page=page)
        self._action_calls = []

    def prepare_action_io(self, node: Node):
        io = types.SimpleNamespace(inputs=dict(node.inputs), outputs={})
        return io

    async def exec_action(self, action_name: str, io):
        self._action_calls.append(action_name)
        io.outputs["result"] = f"ran:{action_name}"

    def extract_outputs(self, node: Node, io):
        self.runtime.set_value("$cur_outputs{result}", io.outputs.get("result"))

    def prepare_control_io(self, node: Node):
        return types.SimpleNamespace(params=dict(node.params))


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

    async def test_temporary_node_runs_in_current_session_without_changing_main_node(self):
        executor = _FakeExecutor(self.flow, self.node)
        self.session._active_executor = executor

        result = await self.session._apply_command(
            "run_temporary_node",
            {
                "node": {
                    "node_id": "temp-1",
                    "name": "Temp Action",
                    "action": "builtin.TempAction",
                    "inputs": {"value": "$flow{value}"},
                }
            },
            executor,
        )

        self.assertEqual(result["current_node_id"], "node-1")
        self.assertFalse(result["jumped"])
        self.assertEqual(result["outputs"]["items"]["result"], "ran:builtin.TempAction")
        self.assertEqual(executor.runtime.current_node_id, "node-1")
        self.assertEqual(executor._action_calls, ["builtin.TempAction"])

    async def test_temporary_node_can_jump_to_target_node(self):
        target = Node(
            node_id="marker",
            name="Marker",
            description="",
            action="",
            control="builtin.NextNode",
        )
        self.flow.nodes.append(target)
        executor = _FakeExecutor(self.flow, self.node)
        executor.runtime.nodes[target.node_id] = target
        self.session._active_executor = executor

        result = await self.session._apply_command(
            "run_temporary_node",
            {
                "node": {
                    "node_id": "temp-2",
                    "name": "Temp Jump",
                    "action": "builtin.TempAction",
                },
                "jump_to_node_id": "marker",
            },
            executor,
        )

        self.assertTrue(result["jumped"])
        self.assertEqual(result["current_node_id"], "marker")
        self.assertEqual(executor.runtime.current_node_id, "marker")

    def test_page_commands_do_not_force_pause_and_use_extended_timeout(self):
        with mock.patch.object(self.session, "dispatch_command", return_value={"ok": True}) as dispatch:
            result = self.manager.page_snapshot(self.session.record.session_id)

        self.assertEqual(result, {"ok": True})
        dispatch.assert_called_once_with("page_snapshot", {}, timeout=90.0, auto_pause=False)

        with mock.patch.object(self.session, "dispatch_command", return_value={"ok": True}) as dispatch:
            result = self.manager.page_run_script(
                self.session.record.session_id,
                "return 1",
                timeout_ms=120000,
            )

        self.assertEqual(result, {"ok": True})
        dispatch.assert_called_once_with(
            "page_run_script",
            {"code": "return 1", "arg": None, "timeout_ms": 120000},
            timeout=135.0,
            auto_pause=False,
        )

    async def test_page_snapshot_can_dispatch_immediately_while_runtime_loop_is_active(self):
        page = _FakePage()
        executor = _FakeExecutor(self.flow, self.node, page=page)
        self.session._active_executor = executor
        self.session._runtime_loop = asyncio.get_running_loop()

        with mock.patch.object(session_module.pw, "Page", _FakePage):
            result = await asyncio.to_thread(
                self.session.dispatch_command,
                "page_snapshot",
                {},
                1.0,
                False,
            )

        self.assertEqual(result["url"], "about:blank")
        self.assertEqual(result["title"], "Fake Page")