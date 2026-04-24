import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime
import ast
import json
import logging
from pathlib import Path
import queue
import threading
import time
from typing import Any
from uuid import uuid4

import playwright.async_api as pw

from weboter.core.workflow_io import WorkflowWriter
from weboter.public.model import Flow, Node, NodeOutputConfig


SESSION_STATUS_CREATED = "created"
SESSION_STATUS_RUNNING = "running"
SESSION_STATUS_PAUSED = "paused"
SESSION_STATUS_GUARD_WAITING = "guard_waiting"
SESSION_STATUS_SUCCEEDED = "succeeded"
SESSION_STATUS_FAILED = "failed"

OBSERVE_PERMISSION = "observe"
CONTROL_PERMISSION = "control"
PAGE_PERMISSION = "page"
WORKFLOW_EDIT_PERMISSION = "workflow_edit"


@dataclass
class SessionRecord:
    session_id: str
    task_id: str
    workflow_path: str
    workflow_name: str
    status: str
    created_at: str
    updated_at: str
    log_path: str
    permissions: list[str] = field(default_factory=list)
    current_node_id: str | None = None
    current_node_name: str | None = None
    current_phase: str | None = None
    pause_reason: str | None = None
    last_error: str | None = None
    snapshot_count: int = 0
    last_snapshot_path: str | None = None
    current_page_url: str | None = None
    current_page_title: str | None = None
    breakpoints: list[dict[str, Any]] = field(default_factory=list)
    last_stop: dict[str, Any] | None = None
    interrupt_requested: bool = False


class SessionHooks:
    def __init__(self, session: "ExecutionSession"):
        self.session = session

    async def on_workflow_loaded(self, executor, flow: Flow) -> None:
        await self.session.on_workflow_loaded(executor, flow)

    async def before_step(self, executor, node: Node) -> None:
        await self.session.before_step(executor, node)

    async def after_step(self, executor, node: Node, next_node_id: str) -> None:
        await self.session.after_step(executor, node, next_node_id)

    async def on_error(self, executor, exc: Exception) -> bool:
        return await self.session.on_error(executor, exc)

    async def on_finished(self, executor) -> None:
        await self.session.on_finished(executor)


class _SessionCommand:
    def __init__(self, action: str, payload: dict[str, Any] | None = None):
        self.action = action
        self.payload = payload or {}
        self.event = threading.Event()
        self.result: Any = None
        self.error: Exception | None = None


class ExecutionSession:
    def __init__(self, manager: "ExecutionSessionManager", record: SessionRecord):
        self.manager = manager
        self.record = record
        self._lock = threading.RLock()
        self._commands: queue.Queue[_SessionCommand] = queue.Queue()
        self._pause_requested = False
        self._guard_waiting = False
        self._abort_requested = False
        self._resume_reason: str | None = None
        self._interrupt_requested = False
        self._breakpoints: list[dict[str, Any]] = []
        self._active_executor = None
        self._runtime_loop: asyncio.AbstractEventLoop | None = None

    def create_hooks(self) -> SessionHooks:
        return SessionHooks(self)

    def request_pause(self, reason: str = "manual") -> dict[str, Any]:
        with self._lock:
            self._pause_requested = True
            self.record.pause_reason = reason
            if self.record.status == SESSION_STATUS_RUNNING:
                self.record.status = SESSION_STATUS_PAUSED
            self.manager._save_record(self.record)
            return asdict(self.record)

    def request_interrupt(self, reason: str = "interrupt_next") -> dict[str, Any]:
        with self._lock:
            self._interrupt_requested = True
            self.record.interrupt_requested = True
            self.record.pause_reason = reason
            self.manager._save_record(self.record)
            return asdict(self.record)

    def configure_breakpoints(self, breakpoints: list[dict[str, Any]], replace: bool = True) -> dict[str, Any]:
        normalized = [self._normalize_breakpoint(item) for item in breakpoints]
        with self._lock:
            if replace:
                self._breakpoints = normalized
            else:
                self._breakpoints.extend(normalized)
            self.record.breakpoints = self._serialize_breakpoints()
            self.manager._save_record(self.record)
            return {
                "session": asdict(self.record),
                "breakpoints": self._serialize_breakpoints(),
            }

    def clear_breakpoints(self, breakpoint_ids: list[str] | None = None) -> dict[str, Any]:
        with self._lock:
            if breakpoint_ids:
                target_ids = set(breakpoint_ids)
                self._breakpoints = [item for item in self._breakpoints if item["id"] not in target_ids]
            else:
                self._breakpoints = []
            self.record.breakpoints = self._serialize_breakpoints()
            self.manager._save_record(self.record)
            return {
                "session": asdict(self.record),
                "breakpoints": self._serialize_breakpoints(),
            }

    def describe_workflow(self) -> dict[str, Any]:
        executor = self._active_executor
        if executor is None or executor.workflow is None:
            raise ValueError(f"Session workflow is not available: {self.record.session_id}")
        workflow = executor.workflow
        workflow_summary = self._serialize_flow_summary(workflow)
        return {
            "session_id": self.record.session_id,
            "task_id": self.record.task_id,
            "current_node_id": executor.runtime.current_node_id,
            "workflow": workflow_summary,
        }

    def describe_workflow_node(self, node_id: str) -> dict[str, Any]:
        executor = self._active_executor
        if executor is None or executor.workflow is None:
            raise ValueError(f"Session workflow is not available: {self.record.session_id}")
        for node in executor.workflow.nodes:
            if node.node_id == node_id:
                return {
                    "session_id": self.record.session_id,
                    "task_id": self.record.task_id,
                    "node": self._serialize_node(node),
                }
        raise FileNotFoundError(f"Workflow node not found: {node_id}")

    def describe_runtime_value(self, key: str) -> dict[str, Any]:
        executor = self._active_executor
        if executor is None:
            raise ValueError(f"Session runtime is not available: {self.record.session_id}")
        value = executor.runtime.get_value(key)
        return {
            "session_id": self.record.session_id,
            "task_id": self.record.task_id,
            "key": key,
            "value": self._serialize_runtime_preview(value, sensitive=key.startswith("$env{")),
        }

    def dispatch_command(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
        auto_pause: bool = True,
    ) -> Any:
        if auto_pause and action not in {"resume", "abort"}:
            self.request_pause(f"command:{action}")
        if self._can_dispatch_immediately(action):
            return self._dispatch_command_immediately(action, payload, timeout)
        command = _SessionCommand(action, payload)
        self._commands.put(command)
        if not command.event.wait(timeout):
            raise TimeoutError(f"Session command timeout: {action}")
        if command.error:
            raise command.error
        return command.result

    def _can_dispatch_immediately(self, action: str) -> bool:
        if action not in {
            "abort",
            "page_snapshot",
            "page_evaluate",
            "page_run_script",
            "page_goto",
            "page_click",
            "page_fill",
        }:
            return False
        return self._runtime_loop is not None and self._runtime_loop.is_running() and self._active_executor is not None

    def _dispatch_command_immediately(self, action: str, payload: dict[str, Any] | None, timeout: float) -> Any:
        if self._runtime_loop is None or self._active_executor is None:
            raise TimeoutError(f"Session command timeout: {action}")
        future = asyncio.run_coroutine_threadsafe(
            self._apply_command(action, payload or {}, self._active_executor),
            self._runtime_loop,
        )
        try:
            return future.result(timeout=timeout)
        except TimeoutError as exc:
            raise TimeoutError(f"Session command timeout: {action}") from exc

    async def on_workflow_loaded(self, executor, flow: Flow) -> None:
        self._active_executor = executor
        self._runtime_loop = asyncio.get_running_loop()
        with self._lock:
            self.record.status = SESSION_STATUS_RUNNING
            self.record.workflow_name = flow.name
            self.record.updated_at = self.manager._now()
            self.manager._save_record(self.record)
        await self.capture_snapshot(executor, phase="loaded")

    async def before_step(self, executor, node: Node) -> None:
        self._active_executor = executor
        self._runtime_loop = asyncio.get_running_loop()
        await self.capture_snapshot(executor, phase="before_step", node=node)
        await self._arm_debug_stop(executor, phase="before_step", node=node)
        await self._wait_for_commands(executor)

    async def after_step(self, executor, node: Node, next_node_id: str) -> None:
        self._active_executor = executor
        self._runtime_loop = asyncio.get_running_loop()
        await self.capture_snapshot(executor, phase="after_step", node=node, next_node_id=next_node_id)
        await self._wait_for_commands(executor)

    async def on_error(self, executor, exc: Exception) -> bool:
        self._active_executor = executor
        self._runtime_loop = asyncio.get_running_loop()
        with self._lock:
            self._guard_waiting = True
            self.record.status = SESSION_STATUS_GUARD_WAITING
            self.record.pause_reason = "guard"
            self.record.last_error = str(exc)
            self.record.updated_at = self.manager._now()
            self.manager._save_record(self.record)
        await self.capture_snapshot(executor, phase="error", error=str(exc))
        await self._wait_for_commands(executor)
        with self._lock:
            if self._abort_requested:
                self.record.status = SESSION_STATUS_FAILED
                self.record.updated_at = self.manager._now()
                self.manager._save_record(self.record)
                return False
            self._guard_waiting = False
            self.record.status = SESSION_STATUS_RUNNING
            self.record.pause_reason = None
            self.record.updated_at = self.manager._now()
            self.manager._save_record(self.record)
        return True

    async def on_finished(self, executor) -> None:
        self._active_executor = executor
        self._runtime_loop = asyncio.get_running_loop()
        await self.capture_snapshot(executor, phase="finished")

    def mark_finished(self, success: bool, error: str | None = None) -> None:
        with self._lock:
            self.record.status = SESSION_STATUS_SUCCEEDED if success else SESSION_STATUS_FAILED
            self.record.last_error = error
            self.record.pause_reason = None
            self.record.updated_at = self.manager._now()
            self.manager._save_record(self.record)
        self._runtime_loop = None

    async def capture_snapshot(
        self,
        executor,
        phase: str,
        node: Node | None = None,
        next_node_id: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        page_info = await self._collect_page_info(executor, detail=False)
        snapshot_index = self.record.snapshot_count + 1
        snapshot = {
            "session_id": self.record.session_id,
            "task_id": self.record.task_id,
            "timestamp": self.manager._now(),
            "index": snapshot_index,
            "phase": phase,
            "current_node_id": executor.runtime.current_node_id,
            "current_node_name": executor.runtime.get_node_name(executor.runtime.current_node_id) if executor.runtime.current_node_id else None,
            "node": self._serialize_node(node),
            "next_node_id": next_node_id,
            "runtime": self._serialize_runtime(executor.runtime.data_context.data),
            "workflow": self._serialize_flow(executor.workflow),
            "debug": {
                "breakpoints": self._serialize_breakpoints(),
                "interrupt_requested": self._interrupt_requested,
                "last_stop": self.record.last_stop,
            },
            "page": page_info,
            "error": error,
        }
        # 错误快照额外展示上一节点的 prev_outputs，方便取证
        if phase == "error":
            snapshot["prev_outputs"] = self._serialize_runtime_preview(
                executor.runtime.data_context.data.get("prev_outputs", {})
            )

        snapshot_path = self.manager.snapshot_root(self.record.session_id) / f"{snapshot_index:05d}_{phase}.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

        with self._lock:
            self.record.snapshot_count = snapshot_index
            self.record.current_phase = phase
            self.record.current_node_id = snapshot["current_node_id"]
            self.record.current_node_name = snapshot["current_node_name"]
            self.record.current_page_url = page_info.get("url") if page_info else None
            self.record.current_page_title = page_info.get("title") if page_info else None
            self.record.last_snapshot_path = str(snapshot_path)
            self.record.breakpoints = self._serialize_breakpoints()
            self.record.interrupt_requested = self._interrupt_requested
            self.record.updated_at = self.manager._now()
            self.manager._save_record(self.record)
        return snapshot

    async def _arm_debug_stop(
        self,
        executor,
        phase: str,
        node: Node | None = None,
        next_node_id: str | None = None,
    ) -> None:
        stop_detail: dict[str, Any] | None = None
        with self._lock:
            if phase == "before_step" and self._interrupt_requested:
                stop_detail = {
                    "type": "interrupt",
                    "phase": phase,
                    "node_id": node.node_id if node else None,
                    "node_name": node.name if node else None,
                    "reason": self.record.pause_reason or "interrupt_next",
                }
                self._interrupt_requested = False
            else:
                matched_breakpoint = self._match_breakpoint(phase, node, next_node_id)
                if matched_breakpoint is not None:
                    stop_detail = {
                        "type": "breakpoint",
                        "phase": phase,
                        "node_id": node.node_id if node else None,
                        "node_name": node.name if node else None,
                        "breakpoint": dict(matched_breakpoint),
                    }
                    if matched_breakpoint.get("once"):
                        self._breakpoints = [item for item in self._breakpoints if item["id"] != matched_breakpoint["id"]]

            if stop_detail is None:
                self.record.breakpoints = self._serialize_breakpoints()
                self.record.interrupt_requested = self._interrupt_requested
                return

            self._pause_requested = True
            self.record.status = SESSION_STATUS_PAUSED
            self.record.pause_reason = stop_detail["type"]
            self.record.last_stop = stop_detail
            self.record.breakpoints = self._serialize_breakpoints()
            self.record.interrupt_requested = self._interrupt_requested
            self.manager._save_record(self.record)

        await self.capture_snapshot(executor, phase="debug_stop", node=node, next_node_id=next_node_id)

    async def _wait_for_commands(self, executor) -> None:
        while self._pause_requested or self._guard_waiting or not self._commands.empty():
            while True:
                try:
                    command = self._commands.get_nowait()
                except queue.Empty:
                    break
                await self._execute_command(command, executor)

            if not (self._pause_requested or self._guard_waiting):
                break

            with self._lock:
                self.record.status = SESSION_STATUS_GUARD_WAITING if self._guard_waiting else SESSION_STATUS_PAUSED
                self.record.updated_at = self.manager._now()
                self.manager._save_record(self.record)
            await asyncio.sleep(0.1)

    async def _execute_command(self, command: _SessionCommand, executor) -> None:
        try:
            result = await self._apply_command(command.action, command.payload, executor)
            command.result = result
        except Exception as exc:
            command.error = exc
        finally:
            command.event.set()

    async def _apply_command(self, action: str, payload: dict[str, Any], executor) -> Any:
        if action == "resume":
            with self._lock:
                self._pause_requested = False
                self._guard_waiting = False
                self.record.pause_reason = None
                self.record.last_stop = None
                self.record.updated_at = self.manager._now()
                self.manager._save_record(self.record)
                return asdict(self.record)

        if action == "abort":
            with self._lock:
                self._abort_requested = True
                self._pause_requested = False
                self._guard_waiting = False
                self.record.pause_reason = None
                self.record.last_stop = None
                self.record.updated_at = self.manager._now()
                self.manager._save_record(self.record)
                return asdict(self.record)

        if action == "interrupt":
            return self.request_interrupt(payload.get("reason") or "interrupt_next")

        if action == "configure_breakpoints":
            return self.configure_breakpoints(payload.get("breakpoints", []), replace=payload.get("replace", True))

        if action == "clear_breakpoints":
            return self.clear_breakpoints(payload.get("breakpoint_ids"))

        if action == "set_context":
            executor.runtime.set_value(payload["key"], payload["value"])
            return {"updated": payload["key"]}

        if action == "jump_to_node":
            executor.runtime.set_current_node(payload["node_id"])
            return {"current_node_id": payload["node_id"]}

        if action == "patch_node":
            node = self._patch_node(executor.workflow, executor.runtime, payload["node_id"], payload["patch"])
            return {"node_id": node.node_id}

        if action == "add_node":
            node = self._build_node(payload["node"])
            executor.workflow.nodes.append(node)
            executor.runtime.nodes[node.node_id] = node
            return {"node_id": node.node_id}

        if action == "run_temporary_node":
            return await self._run_temporary_node(
                executor,
                payload["node"],
                jump_to_node_id=payload.get("jump_to_node_id"),
            )

        if action == "export_workflow":
            output_path = Path(payload["path"]).expanduser().resolve()
            WorkflowWriter.to_json(executor.workflow, output_path)
            return {"saved": str(output_path)}

        if action == "page_snapshot":
            return await self._collect_page_info(executor, detail=True)

        if action == "page_evaluate":
            page = self._require_page(executor)
            return await page.evaluate(payload["script"], payload.get("arg"))

        if action == "page_run_script":
            return await self._run_page_script(
                executor,
                payload["code"],
                payload.get("arg"),
                payload.get("timeout_ms", 5000),
            )

        if action == "page_goto":
            page = self._require_page(executor)
            await page.goto(payload["url"])
            return await self._collect_page_info(executor, detail=True)

        if action == "page_click":
            page = self._require_page(executor)
            await page.locator(payload["locator"]).click(timeout=payload.get("timeout", 5000))
            return {"clicked": payload["locator"]}

        if action == "page_fill":
            page = self._require_page(executor)
            await page.locator(payload["locator"]).fill(payload["value"], timeout=payload.get("timeout", 5000))
            return {"filled": payload["locator"]}

        raise ValueError(f"Unsupported session command: {action}")

    async def _run_page_script(self, executor, code: str, arg: Any = None, timeout_ms: int = 5000) -> dict[str, Any]:
        page = self._require_page(executor)
        try:
            compiled = self._compile_page_script(code)
        except ValueError as exc:
            raise ValueError(
                f"页面脚本编译失败: {exc}\n"
                "脚本格式说明: 使用 Python 3 异步语法\n"
                "可用内置: len str int float bool dict list tuple set min max sum range enumerate zip sorted any all abs\n"
                "可用变量: page(当前页面), context(session_id task_id workflow runtime current_node_id arg)\n"
                "举例: result = await page.title(); return {\"title\": result}"
            ) from exc
        script_globals = {
            "__builtins__": self._safe_script_builtins(),
        }
        script_locals: dict[str, Any] = {}
        exec(compiled, script_globals, script_locals)
        runner = script_locals["__weboter_page_script__"]
        runtime_snapshot = self._serialize_runtime_preview(executor.runtime.data_context.data)
        workflow_snapshot = self._serialize_flow_summary(executor.workflow)
        context = {
            "session_id": self.record.session_id,
            "task_id": self.record.task_id,
            "workflow": workflow_snapshot,
            "runtime": runtime_snapshot,
            "current_node_id": executor.runtime.current_node_id,
            "arg": arg,
        }
        result = await asyncio.wait_for(runner(page, context), timeout=max(timeout_ms, 1) / 1000)
        page_info = await self._collect_page_info(executor, detail=True)
        snapshot = await self.capture_snapshot(executor, phase="page_script")
        return {
            "result": self._serialize_runtime_preview(result),
            "page": page_info,
            "snapshot": {
                "index": snapshot["index"],
                "phase": snapshot["phase"],
                "timestamp": snapshot["timestamp"],
            },
        }

    async def _collect_page_info(self, executor, detail: bool = False) -> dict[str, Any] | None:
        page = executor.runtime.get_value("$global{{current_page}}")
        if not page:
            return None

        page_info: dict[str, Any] = {
            "url": getattr(page, "url", None),
        }

        try:
            page_info["title"] = await page.title()
        except Exception as exc:
            page_info["title_error"] = str(exc)

        if detail:
            base_name = f"page_{int(time.time() * 1000)}"
            session_root = self.manager.session_root(self.record.session_id)
            session_root.mkdir(parents=True, exist_ok=True)
            html_path = session_root / f"{base_name}.html"
            screenshot_path = session_root / f"{base_name}.png"
            try:
                html = await page.content()
                html_path.write_text(html, encoding="utf-8")
                page_info["html_path"] = str(html_path)
            except Exception as exc:
                page_info["html_error"] = str(exc)
            try:
                await page.screenshot(path=str(screenshot_path), full_page=True)
                page_info["screenshot_path"] = str(screenshot_path)
            except Exception as exc:
                page_info["screenshot_error"] = str(exc)

        return page_info

    def _require_page(self, executor):
        page = executor.runtime.get_value("$global{{current_page}}")
        if not page:
            raise ValueError("Current page is not available in this session")
        if not isinstance(page, pw.Page):
            raise ValueError("Current page handle is invalid")
        return page

    @staticmethod
    def _safe_script_builtins() -> dict[str, Any]:
        return {
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "dict": dict,
            "list": list,
            "tuple": tuple,
            "set": set,
            "min": min,
            "max": max,
            "sum": sum,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "sorted": sorted,
            "any": any,
            "all": all,
            "abs": abs,
        }

    @classmethod
    def _compile_page_script(cls, code: str):
        """编译页面脚本。脚本语言为 Python 3，必须定义异步函数。

        合法举例::

            result = await page.title()
            return {"title": result}

        可用内置: len str int float bool dict list tuple set min max sum range enumerate zip sorted any all abs
        可用内置变量: page(当前页面), context(session_id task_id workflow runtime current_node_id arg)
        不允许: import, global, nonlocal, 类定义, 双下划线名称
        """
        source = code.strip()
        if not source:
            raise ValueError("页面脚本不能为空")
        try:
            tree = ast.parse(source, mode="exec")
        except SyntaxError as exc:
            raise ValueError(f"页面脚本语法错误: {exc}\n示例: result = await page.title(); return {{\"title\": result}}") from exc

        forbidden_nodes = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.ClassDef)
        for node in ast.walk(tree):
            if isinstance(node, forbidden_nodes):
                raise ValueError(
                    f"页面脚本不允许使用 {type(node).__name__}"
                    "\n说明: 脚本运行在受限环境中，无法导入外部模块或定义类"
                )
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                raise ValueError("页面脚本不允许访问双下划线名称")
            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                raise ValueError("页面脚本不允许访问双下划线属性")

        indented = "\n".join(f"    {line}" if line.strip() else "" for line in source.splitlines())
        wrapped = (
            "async def __weboter_page_script__(page, context):\n"
            f"{indented}\n"
        )
        return compile(wrapped, "<weboter-page-script>", "exec")

    @staticmethod
    def _serialize_runtime(data: Any, sensitive: bool = False) -> Any:
        if sensitive:
            return ExecutionSession._mask_runtime_value(data)
        if isinstance(data, (str, int, float, bool)) or data is None:
            return data
        if isinstance(data, Path):
            return str(data)
        if isinstance(data, dict):
            return {
                str(key): ExecutionSession._serialize_runtime(value, sensitive=(str(key) == "env"))
                for key, value in data.items()
            }
        if isinstance(data, list):
            return [ExecutionSession._serialize_runtime(item, sensitive=sensitive) for item in data]
        if isinstance(data, tuple):
            return [ExecutionSession._serialize_runtime(item, sensitive=sensitive) for item in data]
        return {"type": type(data).__name__, "repr": repr(data)}

    @staticmethod
    def _serialize_runtime_preview(data: Any, depth: int = 0, sensitive: bool = False) -> Any:
        if sensitive:
            return ExecutionSession._mask_runtime_value(data)
        if depth >= 2:
            if isinstance(data, dict):
                return {
                    "type": "dict",
                    "key_count": len(data),
                    "keys": sorted(str(key) for key in list(data.keys())[:20]),
                }
            if isinstance(data, (list, tuple)):
                return {
                    "type": type(data).__name__,
                    "item_count": len(data),
                }
            if isinstance(data, str):
                return ExecutionSession._truncate_string(data, 300)
            return ExecutionSession._serialize_runtime(data)

        if isinstance(data, dict):
            keys = list(data.keys())
            items = {}
            for key in keys[:20]:
                items[str(key)] = ExecutionSession._serialize_runtime_preview(
                    data[key],
                    depth + 1,
                    sensitive=(str(key) == "env"),
                )
            return {
                "type": "dict",
                "key_count": len(data),
                "items": items,
                "truncated": len(keys) > 20,
            }
        if isinstance(data, list):
            return {
                "type": "list",
                "item_count": len(data),
                "items": [ExecutionSession._serialize_runtime_preview(item, depth + 1, sensitive=sensitive) for item in data[:20]],
                "truncated": len(data) > 20,
            }
        if isinstance(data, tuple):
            return {
                "type": "tuple",
                "item_count": len(data),
                "items": [ExecutionSession._serialize_runtime_preview(item, depth + 1, sensitive=sensitive) for item in list(data)[:20]],
                "truncated": len(data) > 20,
            }
        if isinstance(data, str):
            return ExecutionSession._truncate_string(data, 500)
        return ExecutionSession._serialize_runtime(data)

    @staticmethod
    def _mask_runtime_value(data: Any) -> Any:
        if data is None:
            return None
        if isinstance(data, str):
            if not data:
                return ""
            if len(data) <= 4:
                return "*" * len(data)
            return f"{data[:2]}***{data[-2:]}"
        if isinstance(data, (int, float, bool)):
            return "***"
        if isinstance(data, dict):
            return {
                "type": "dict",
                "key_count": len(data),
                "keys": sorted(str(key) for key in data.keys()),
                "masked": True,
            }
        if isinstance(data, list):
            return {"type": "list", "item_count": len(data), "masked": True}
        if isinstance(data, tuple):
            return {"type": "tuple", "item_count": len(data), "masked": True}
        return "***"

    @staticmethod
    def _truncate_string(value: str, limit: int) -> dict[str, Any] | str:
        if len(value) <= limit:
            return value
        return {
            "type": "string",
            "length": len(value),
            "preview": value[:limit],
            "truncated": True,
        }

    @staticmethod
    def _serialize_node(node: Node | None) -> dict[str, Any] | None:
        if node is None:
            return None
        return {
            "node_id": node.node_id,
            "name": node.name,
            "description": node.description,
            "action": node.action,
            "control": node.control,
            "inputs": node.inputs,
            "params": node.params,
            "outputs": [asdict(item) for item in node.outputs],
            "log": node.log,
        }

    @staticmethod
    def _serialize_node_summary(node: Node) -> dict[str, Any]:
        return {
            "node_id": node.node_id,
            "name": node.name,
            "action": node.action,
            "control": node.control,
            "log": node.log,
        }

    @staticmethod
    def _serialize_flow(flow: Flow | None) -> dict[str, Any] | None:
        if flow is None:
            return None
        return {
            "flow_id": flow.flow_id,
            "name": flow.name,
            "description": flow.description,
            "start_node_id": flow.start_node_id,
            "log": flow.log,
            "nodes": [ExecutionSession._serialize_node(item) for item in flow.nodes],
        }

    @staticmethod
    def _serialize_flow_summary(flow: Flow | None) -> dict[str, Any] | None:
        if flow is None:
            return None
        node_summaries = [ExecutionSession._serialize_node_summary(item) for item in flow.nodes[:20]]
        return {
            "flow_id": flow.flow_id,
            "name": flow.name,
            "description": flow.description,
            "start_node_id": flow.start_node_id,
            "log": flow.log,
            "node_count": len(flow.nodes),
            "nodes": node_summaries,
            "remaining_node_count": max(len(flow.nodes) - len(node_summaries), 0),
            "available_detail_methods": [
                "session_workflow_node_detail(node_id)",
            ],
        }

    @staticmethod
    def _normalize_breakpoint(data: dict[str, Any]) -> dict[str, Any]:
        phase = (data.get("phase") or "before_step").strip() or "before_step"
        node_id = (data.get("node_id") or "").strip() or None
        node_name = (data.get("node_name") or "").strip() or None
        if node_id is None and node_name is None:
            raise ValueError("断点至少需要 node_id 或 node_name")
        return {
            "id": (data.get("id") or uuid4().hex[:8]).strip(),
            "phase": phase,
            "node_id": node_id,
            "node_name": node_name,
            "enabled": bool(data.get("enabled", True)),
            "once": bool(data.get("once", False)),
        }

    def _serialize_breakpoints(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._breakpoints]

    def _match_breakpoint(self, phase: str, node: Node | None, next_node_id: str | None = None) -> dict[str, Any] | None:
        for item in self._breakpoints:
            if not item.get("enabled", True):
                continue
            if item.get("phase") not in {phase, "*"}:
                continue
            if item.get("node_id") and (node is None or item["node_id"] != node.node_id):
                continue
            if item.get("node_name") and (node is None or item["node_name"] != node.name):
                continue
            if item.get("next_node_id") and item.get("next_node_id") != next_node_id:
                continue
            return item
        return None

    @staticmethod
    def _build_node(data: dict[str, Any]) -> Node:
        node_id = data.get("node_id") or f"runtime_{uuid4().hex[:8]}"
        return Node(
            node_id=node_id,
            name=data.get("name", node_id),
            description=data.get("description", ""),
            action=data.get("action", ""),
            inputs=data.get("inputs", {}),
            outputs=[NodeOutputConfig(**item) for item in data.get("outputs", [])],
            control=data.get("control", ""),
            params=data.get("params", {}),
            log=data.get("log", "short"),
        )

    async def _run_temporary_node(
        self,
        executor,
        node_data: dict[str, Any],
        jump_to_node_id: str | None = None,
    ) -> dict[str, Any]:
        node = self._build_node(node_data)
        previous_node_id = executor.runtime.current_node_id
        original_node = executor.runtime.nodes.get(node.node_id)
        executor.runtime.nodes[node.node_id] = node
        executor.runtime.current_node_id = node.node_id

        try:
            action_io = executor.prepare_action_io(node)
            if node.action:
                await executor.exec_action(node.action, action_io)
                executor.extract_outputs(node, action_io)

            if jump_to_node_id:
                executor.runtime.set_current_node(jump_to_node_id)
                executor.runtime.switch_outputs()
            else:
                executor.runtime.current_node_id = previous_node_id

            snapshot = await self.capture_snapshot(
                executor,
                phase="temporary_node",
                node=node,
                next_node_id=jump_to_node_id,
            )
            return {
                "node": self._serialize_node(node),
                "jumped": bool(jump_to_node_id),
                "current_node_id": executor.runtime.current_node_id,
                "outputs": self._serialize_runtime_preview(action_io.outputs),
                "snapshot_index": snapshot["index"],
            }
        finally:
            if original_node is None:
                executor.runtime.nodes.pop(node.node_id, None)
            else:
                executor.runtime.nodes[node.node_id] = original_node
            if not jump_to_node_id:
                executor.runtime.current_node_id = previous_node_id

    @staticmethod
    def _patch_node(flow: Flow, runtime, node_id: str, patch: dict[str, Any]) -> Node:
        if node_id not in runtime.nodes:
            raise KeyError(f"节点ID未找到: {node_id}")
        node = runtime.nodes[node_id]
        for key in ["name", "description", "action", "control", "log"]:
            if key in patch:
                setattr(node, key, patch[key])
        if "inputs" in patch:
            node.inputs = patch["inputs"]
        if "params" in patch:
            node.params = patch["params"]
        if "outputs" in patch:
            node.outputs = [NodeOutputConfig(**item) for item in patch["outputs"]]
        return node


class ExecutionSessionManager:
    def __init__(self, root: Path, system_logger: logging.Logger):
        self.root = root
        self.system_logger = system_logger
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._live_sessions: dict[str, ExecutionSession] = {}

    def create_session(
        self,
        task_id: str,
        workflow_path: Path,
        workflow_name: str,
        log_path: Path,
        permissions: list[str] | None = None,
        pause_before_start: bool = False,
        breakpoints: list[dict[str, Any]] | None = None,
    ) -> ExecutionSession:
        record = SessionRecord(
            session_id=task_id,
            task_id=task_id,
            workflow_path=str(workflow_path),
            workflow_name=workflow_name,
            status=SESSION_STATUS_CREATED,
            created_at=self._now(),
            updated_at=self._now(),
            log_path=str(log_path),
            permissions=permissions or [OBSERVE_PERMISSION, CONTROL_PERMISSION, PAGE_PERMISSION, WORKFLOW_EDIT_PERMISSION],
        )
        session = ExecutionSession(self, record)
        if breakpoints:
            session.configure_breakpoints(breakpoints)
        if pause_before_start:
            session.request_interrupt("start_before_first_node")
        with self._lock:
            self._live_sessions[record.session_id] = session
            self._save_record(record)
        return session

    def list_sessions(self, limit: int = 20) -> list[SessionRecord]:
        session_files = sorted(self.root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        return [self._load_record(path) for path in session_files[:limit]]

    def get_session(self, session_id: str) -> SessionRecord:
        return self._load_record(self._resolve_session_file(session_id))

    def get_live_session(self, session_id: str) -> ExecutionSession | None:
        resolved_id = self._resolve_session_file(session_id).stem
        return self._live_sessions.get(resolved_id)

    def get_snapshots(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        session = self.get_session(session_id)
        snapshot_files = sorted(self.snapshot_root(session.session_id).glob("*.json"), reverse=True)
        return [self._snapshot_summary(json.loads(path.read_text(encoding="utf-8"))) for path in snapshot_files[:limit]]

    def get_snapshot_detail(
        self,
        session_id: str,
        snapshot_index: int,
        sections: list[str] | None = None,
    ) -> dict[str, Any]:
        session = self.get_session(session_id)
        path = self._resolve_snapshot_file(session.session_id, snapshot_index)
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        return self._snapshot_detail(snapshot, sections)

    def request_pause(self, session_id: str, reason: str = "manual") -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.request_pause(reason)

    def request_interrupt(self, session_id: str, reason: str = "interrupt_next") -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.request_interrupt(reason)

    def resume(self, session_id: str) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("resume")

    def abort(self, session_id: str) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("abort", auto_pause=False)

    def set_context(self, session_id: str, key: str, value: Any) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("set_context", {"key": key, "value": value})

    def jump_to_node(self, session_id: str, node_id: str) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("jump_to_node", {"node_id": node_id})

    def patch_node(self, session_id: str, node_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("patch_node", {"node_id": node_id, "patch": patch})

    def add_node(self, session_id: str, node: dict[str, Any]) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("add_node", {"node": node})

    def run_temporary_node(
        self,
        session_id: str,
        node: dict[str, Any],
        jump_to_node_id: str | None = None,
    ) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        payload = {"node": node, "jump_to_node_id": jump_to_node_id}
        return session.dispatch_command("run_temporary_node", payload)

    def export_workflow(self, session_id: str, path: str) -> dict[str, Any]:
        live = self.get_live_session(session_id)
        if live is not None:
            return live.dispatch_command("export_workflow", {"path": path})
        # 已终止 session: 从最新快照重建 workflow JSON 并写入目标路径
        snap_data = self._workflow_from_snapshot(session_id)
        workflow_dict = snap_data.get("workflow")
        if not workflow_dict:
            raise ValueError(f"No workflow data available to export for session: {session_id}")
        output_path = Path(path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # 完整 workflow 数据来自快照的 workflow 字段（已完整序列化）
        record = self.get_session(session_id)
        snapshot_files = sorted(self.snapshot_root(record.session_id).glob("*.json"), reverse=True)
        for snap_file in snapshot_files:
            try:
                snap = json.loads(snap_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if snap.get("workflow") is None:
                continue
            output_path.write_text(
                json.dumps(snap["workflow"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {"saved": str(output_path), "source": "snapshot", "snapshot_index": snap.get("index")}
        raise ValueError(f"No workflow data available to export for session: {session_id}")

    def get_workflow(self, session_id: str) -> dict[str, Any]:
        live = self.get_live_session(session_id)
        if live is not None:
            return live.describe_workflow()
        return self._workflow_from_snapshot(session_id)

    def get_workflow_node(self, session_id: str, node_id: str) -> dict[str, Any]:
        live = self.get_live_session(session_id)
        if live is not None:
            return live.describe_workflow_node(node_id)
        snapshot_wf = self._workflow_from_snapshot(session_id)
        nodes = (snapshot_wf.get("workflow") or {}).get("nodes") or []
        for node in nodes:
            if node.get("node_id") == node_id:
                return {
                    "session_id": session_id,
                    "task_id": snapshot_wf.get("task_id"),
                    "node": node,
                    "source": "snapshot",
                }
        raise FileNotFoundError(f"Workflow node not found: {node_id}")

    def _workflow_from_snapshot(self, session_id: str) -> dict[str, Any]:
        """从该 session 最新快照中读取 workflow 摘要，用于已终止 session 的 workflow 查询"""
        record = self.get_session(session_id)
        snapshot_files = sorted(self.snapshot_root(record.session_id).glob("*.json"), reverse=True)
        if not snapshot_files:
            raise ValueError(f"Session has no snapshots: {session_id}")
        for snap_file in snapshot_files:
            try:
                snap = json.loads(snap_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            workflow = snap.get("workflow")
            if workflow is None:
                continue
            nodes = workflow.get("nodes") or []
            node_summaries = nodes[:20]
            return {
                "session_id": session_id,
                "task_id": snap.get("task_id"),
                "current_node_id": snap.get("current_node_id"),
                "workflow": {
                    "flow_id": workflow.get("flow_id"),
                    "name": workflow.get("name"),
                    "description": workflow.get("description"),
                    "start_node_id": workflow.get("start_node_id"),
                    "log": workflow.get("log"),
                    "node_count": len(nodes),
                    "nodes": node_summaries,
                    "remaining_node_count": max(len(nodes) - len(node_summaries), 0),
                    "available_detail_methods": ["session_workflow_node_detail(node_id)"],
                },
                "source": "snapshot",
                "snapshot_index": snap.get("index"),
            }
        raise ValueError(f"No workflow data found in snapshots for session: {session_id}")

    def get_runtime_value(self, session_id: str, key: str) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.describe_runtime_value(key)

    def configure_breakpoints(
        self,
        session_id: str,
        breakpoints: list[dict[str, Any]],
        replace: bool = True,
    ) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.configure_breakpoints(breakpoints, replace=replace)

    def clear_breakpoints(self, session_id: str, breakpoint_ids: list[str] | None = None) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.clear_breakpoints(breakpoint_ids)

    def page_snapshot(self, session_id: str) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("page_snapshot", {}, timeout=90.0, auto_pause=False)

    def page_evaluate(self, session_id: str, script: str, arg: Any = None) -> Any:
        session = self._require_live_session(session_id)
        return session.dispatch_command("page_evaluate", {"script": script, "arg": arg}, timeout=60.0, auto_pause=False)

    def page_run_script(self, session_id: str, code: str, arg: Any = None, timeout_ms: int = 5000) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command(
            "page_run_script",
            {"code": code, "arg": arg, "timeout_ms": timeout_ms},
            timeout=max(60.0, timeout_ms / 1000 + 15.0),
            auto_pause=False,
        )

    def page_goto(self, session_id: str, url: str) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("page_goto", {"url": url}, timeout=60.0, auto_pause=False)

    def page_click(self, session_id: str, locator: str, timeout: int = 5000) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("page_click", {"locator": locator, "timeout": timeout}, timeout=60.0, auto_pause=False)

    def page_fill(self, session_id: str, locator: str, value: str, timeout: int = 5000) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("page_fill", {"locator": locator, "value": value, "timeout": timeout}, timeout=60.0, auto_pause=False)

    def mark_session_finished(self, session_id: str, success: bool, error: str | None = None) -> None:
        session = self._live_sessions.get(session_id)
        if session is None:
            record = self.get_session(session_id)
            record.status = SESSION_STATUS_SUCCEEDED if success else SESSION_STATUS_FAILED
            record.last_error = error
            record.updated_at = self._now()
            self._save_record(record)
            return
        session.mark_finished(success, error)
        with self._lock:
            self._live_sessions.pop(session_id, None)

    # --- 会话清理 ---

    _TERMINAL_STATUSES = frozenset({SESSION_STATUS_SUCCEEDED, SESSION_STATUS_FAILED})

    def delete_session(self, session_id: str) -> dict[str, Any]:
        """删除一个已终止的 session（记录文件 + 快照目录）。
        若 session 仍处于活动状态则拒绝操作。
        """
        record = self.get_session(session_id)
        if record.status not in self._TERMINAL_STATUSES:
            raise ValueError(
                f"只能删除已终止的 session（{', '.join(sorted(self._TERMINAL_STATUSES))}），"
                f"当前状态为 {record.status!r}"
            )
        with self._lock:
            self._live_sessions.pop(record.session_id, None)
        session_dir = self.session_root(record.session_id)
        record_file = self._resolve_session_file(record.session_id)
        snapshot_count = record.snapshot_count
        import shutil
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
        if record_file.exists():
            record_file.unlink(missing_ok=True)
        return {
            "session_id": record.session_id,
            "deleted": True,
            "snapshot_count": snapshot_count,
        }

    def cleanup_sessions(
        self,
        statuses: list[str] | None = None,
        max_age_hours: float | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """批量清理已终止的 session。
        - statuses: 限定清理的状态（默认仅终止态：succeeded / failed）
        - max_age_hours: 仅删除 updated_at 距今超过指定小时数的 session
        - limit: 单次最多清理数量，避免误操作过大
        """
        import shutil
        from datetime import datetime, timezone

        allowed_statuses = set(statuses) if statuses else self._TERMINAL_STATUSES
        # 只允许清理终止态，忽略请求中混入的活动态
        allowed_statuses &= self._TERMINAL_STATUSES

        session_files = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime)
        deleted = []
        skipped = []
        now = datetime.now(tz=timezone.utc)

        for path in session_files:
            if len(deleted) >= limit:
                break
            try:
                record = self._load_record(path)
            except Exception:
                continue
            if record.status not in allowed_statuses:
                continue
            if max_age_hours is not None:
                try:
                    updated = datetime.fromisoformat(record.updated_at)
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=timezone.utc)
                    age_hours = (now - updated).total_seconds() / 3600
                    if age_hours < max_age_hours:
                        skipped.append(record.session_id)
                        continue
                except Exception:
                    pass
            with self._lock:
                self._live_sessions.pop(record.session_id, None)
            session_dir = self.session_root(record.session_id)
            if session_dir.exists():
                shutil.rmtree(session_dir, ignore_errors=True)
            path.unlink(missing_ok=True)
            deleted.append(record.session_id)

        return {
            "deleted_count": len(deleted),
            "deleted": deleted,
            "skipped_count": len(skipped),
        }

    def session_root(self, session_id: str) -> Path:
        return self.root / session_id

    def snapshot_root(self, session_id: str) -> Path:
        return self.session_root(session_id) / "snapshots"

    def _resolve_snapshot_file(self, session_id: str, snapshot_index: int) -> Path:
        matches = sorted(self.snapshot_root(session_id).glob(f"{snapshot_index:05d}_*.json"))
        if not matches:
            raise FileNotFoundError(f"Snapshot not found: session={session_id} index={snapshot_index}")
        return matches[0]

    @staticmethod
    def _snapshot_sections(snapshot: dict[str, Any]) -> list[str]:
        sections: list[str] = []
        if snapshot.get("node") is not None:
            sections.append("node")
        if snapshot.get("runtime") is not None:
            sections.append("runtime")
        if snapshot.get("workflow") is not None:
            sections.append("workflow")
        if snapshot.get("page") is not None:
            sections.append("page")
        if snapshot.get("debug") is not None:
            sections.append("debug")
        if snapshot.get("error") is not None:
            sections.append("error")
        if snapshot.get("prev_outputs") is not None:
            sections.append("prev_outputs")
        return sections

    @classmethod
    def _snapshot_summary(cls, snapshot: dict[str, Any]) -> dict[str, Any]:
        page = snapshot.get("page") or {}
        workflow = snapshot.get("workflow") or {}
        runtime = snapshot.get("runtime") or {}
        node = snapshot.get("node") or {}
        return {
            "session_id": snapshot.get("session_id"),
            "task_id": snapshot.get("task_id"),
            "index": snapshot.get("index"),
            "timestamp": snapshot.get("timestamp"),
            "phase": snapshot.get("phase"),
            "current_node_id": snapshot.get("current_node_id"),
            "current_node_name": snapshot.get("current_node_name"),
            "next_node_id": snapshot.get("next_node_id"),
            "error": snapshot.get("error"),
            "node_summary": {
                "node_id": node.get("node_id"),
                "name": node.get("name"),
                "action": node.get("action"),
                "control": node.get("control"),
            } if node else None,
            "page_summary": {
                "url": page.get("url"),
                "title": page.get("title"),
            } if page else None,
            "runtime_summary": {
                "top_level_keys": sorted(runtime.keys()) if isinstance(runtime, dict) else None,
            },
            "workflow_summary": {
                "flow_id": workflow.get("flow_id"),
                "name": workflow.get("name"),
                "start_node_id": workflow.get("start_node_id"),
                "node_count": len(workflow.get("nodes") or []),
            } if workflow else None,
            "debug_summary": {
                "last_stop": (snapshot.get("debug") or {}).get("last_stop"),
                "interrupt_requested": (snapshot.get("debug") or {}).get("interrupt_requested"),
                "breakpoint_count": len((snapshot.get("debug") or {}).get("breakpoints") or []),
            } if snapshot.get("debug") is not None else None,
            "available_sections": cls._snapshot_sections(snapshot),
        }

    @classmethod
    def _snapshot_detail(cls, snapshot: dict[str, Any], sections: list[str] | None = None) -> dict[str, Any]:
        detail = cls._snapshot_summary(snapshot)
        requested = cls._normalize_snapshot_sections(sections)
        if not requested:
            return detail
        workflow = snapshot.get("workflow") or {}
        runtime = snapshot.get("runtime")
        section_map = {
            "node": snapshot.get("node"),
            "runtime": ExecutionSession._serialize_runtime_preview(runtime),
            "workflow": {
                "flow_id": workflow.get("flow_id"),
                "name": workflow.get("name"),
                "start_node_id": workflow.get("start_node_id"),
                "node_count": len(workflow.get("nodes") or []),
                "available_detail_methods": [
                    "session_workflow_node_detail(node_id)",
                    "session_runtime_value(key)",
                ],
            } if workflow else None,
            "page": snapshot.get("page"),
            "debug": snapshot.get("debug"),
            "error": snapshot.get("error"),
            "prev_outputs": snapshot.get("prev_outputs"),
        }
        detail["sections"] = {name: section_map[name] for name in requested if name in section_map}
        return detail

    @staticmethod
    def _normalize_snapshot_sections(sections: list[str] | None) -> list[str]:
        if not sections:
            return []
        allowed = {"node", "runtime", "workflow", "page", "debug", "error", "prev_outputs"}
        normalized: list[str] = []
        for item in sections:
            name = item.strip().lower()
            if not name:
                continue
            if name not in allowed:
                raise ValueError(f"Unsupported snapshot section: {item}")
            if name not in normalized:
                normalized.append(name)
        return normalized

    def _require_live_session(self, session_id: str) -> ExecutionSession:
        session = self.get_live_session(session_id)
        if session is None:
            raise ValueError(f"Session is not active: {session_id}")
        return session

    def _save_record(self, record: SessionRecord) -> None:
        record.updated_at = self._now()
        with self._lock:
            path = self.root / f"{record.session_id}.json"
            temp_path = path.with_suffix(".json.tmp")
            with open(temp_path, "w", encoding="utf-8") as file_obj:
                json.dump(asdict(record), file_obj, ensure_ascii=False, indent=2)
            temp_path.replace(path)

    def _load_record(self, path: Path) -> SessionRecord:
        with open(path, "r", encoding="utf-8") as file_obj:
            return SessionRecord(**json.load(file_obj))

    def _resolve_session_file(self, session_id: str) -> Path:
        exact = self.root / f"{session_id}.json"
        if exact.is_file():
            return exact
        matches = sorted(self.root.glob(f"{session_id}*.json"))
        if not matches:
            raise FileNotFoundError(f"Session not found: {session_id}")
        if len(matches) > 1:
            candidates = ", ".join(path.stem for path in matches[:5])
            raise ValueError(f"Session id prefix is ambiguous: {session_id} -> {candidates}")
        return matches[0]

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")