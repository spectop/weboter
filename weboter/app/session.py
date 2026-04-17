import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import logging
from pathlib import Path
import queue
import threading
import time
from typing import Any

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

    def dispatch_command(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
        auto_pause: bool = True,
    ) -> Any:
        if auto_pause and action not in {"resume", "abort"}:
            self.request_pause(f"command:{action}")
        command = _SessionCommand(action, payload)
        self._commands.put(command)
        if not command.event.wait(timeout):
            raise TimeoutError(f"Session command timeout: {action}")
        if command.error:
            raise command.error
        return command.result

    async def on_workflow_loaded(self, executor, flow: Flow) -> None:
        with self._lock:
            self.record.status = SESSION_STATUS_RUNNING
            self.record.workflow_name = flow.name
            self.record.updated_at = self.manager._now()
            self.manager._save_record(self.record)
        await self.capture_snapshot(executor, phase="loaded")

    async def before_step(self, executor, node: Node) -> None:
        await self.capture_snapshot(executor, phase="before_step", node=node)
        await self._wait_for_commands(executor)

    async def after_step(self, executor, node: Node, next_node_id: str) -> None:
        await self.capture_snapshot(executor, phase="after_step", node=node, next_node_id=next_node_id)
        await self._wait_for_commands(executor)

    async def on_error(self, executor, exc: Exception) -> bool:
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
        await self.capture_snapshot(executor, phase="finished")

    def mark_finished(self, success: bool, error: str | None = None) -> None:
        with self._lock:
            self.record.status = SESSION_STATUS_SUCCEEDED if success else SESSION_STATUS_FAILED
            self.record.last_error = error
            self.record.pause_reason = None
            self.record.updated_at = self.manager._now()
            self.manager._save_record(self.record)

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
            "page": page_info,
            "error": error,
        }

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
            self.record.updated_at = self.manager._now()
            self.manager._save_record(self.record)
        return snapshot

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
                self.record.updated_at = self.manager._now()
                self.manager._save_record(self.record)
                return asdict(self.record)

        if action == "abort":
            with self._lock:
                self._abort_requested = True
                self._pause_requested = False
                self._guard_waiting = False
                self.record.pause_reason = None
                self.record.updated_at = self.manager._now()
                self.manager._save_record(self.record)
                return asdict(self.record)

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

        if action == "export_workflow":
            output_path = Path(payload["path"]).expanduser().resolve()
            WorkflowWriter.to_json(executor.workflow, output_path)
            return {"saved": str(output_path)}

        if action == "page_snapshot":
            return await self._collect_page_info(executor, detail=True)

        if action == "page_evaluate":
            page = self._require_page(executor)
            return await page.evaluate(payload["script"], payload.get("arg"))

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
    def _serialize_runtime(data: Any) -> Any:
        if isinstance(data, (str, int, float, bool)) or data is None:
            return data
        if isinstance(data, Path):
            return str(data)
        if isinstance(data, dict):
            return {str(key): ExecutionSession._serialize_runtime(value) for key, value in data.items()}
        if isinstance(data, list):
            return [ExecutionSession._serialize_runtime(item) for item in data]
        if isinstance(data, tuple):
            return [ExecutionSession._serialize_runtime(item) for item in data]
        return {"type": type(data).__name__, "repr": repr(data)}

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
    def _build_node(data: dict[str, Any]) -> Node:
        return Node(
            node_id=data["node_id"],
            name=data.get("name", data["node_id"]),
            description=data.get("description", ""),
            action=data.get("action", ""),
            inputs=data.get("inputs", {}),
            outputs=[NodeOutputConfig(**item) for item in data.get("outputs", [])],
            control=data.get("control", ""),
            params=data.get("params", {}),
            log=data.get("log", "short"),
        )

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
        return [json.loads(path.read_text(encoding="utf-8")) for path in snapshot_files[:limit]]

    def request_pause(self, session_id: str, reason: str = "manual") -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.request_pause(reason)

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

    def export_workflow(self, session_id: str, path: str) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("export_workflow", {"path": path})

    def page_snapshot(self, session_id: str) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("page_snapshot", {})

    def page_evaluate(self, session_id: str, script: str, arg: Any = None) -> Any:
        session = self._require_live_session(session_id)
        return session.dispatch_command("page_evaluate", {"script": script, "arg": arg})

    def page_goto(self, session_id: str, url: str) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("page_goto", {"url": url})

    def page_click(self, session_id: str, locator: str, timeout: int = 5000) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("page_click", {"locator": locator, "timeout": timeout})

    def page_fill(self, session_id: str, locator: str, value: str, timeout: int = 5000) -> dict[str, Any]:
        session = self._require_live_session(session_id)
        return session.dispatch_command("page_fill", {"locator": locator, "value": value, "timeout": timeout})

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

    def session_root(self, session_id: str) -> Path:
        return self.root / session_id

    def snapshot_root(self, session_id: str) -> Path:
        return self.session_root(session_id) / "snapshots"

    def _require_live_session(self, session_id: str) -> ExecutionSession:
        session = self.get_live_session(session_id)
        if session is None:
            raise ValueError(f"Session is not active: {session_id}")
        return session

    def _save_record(self, record: SessionRecord) -> None:
        record.updated_at = self._now()
        with self._lock:
            with open(self.root / f"{record.session_id}.json", "w", encoding="utf-8") as file_obj:
                json.dump(asdict(record), file_obj, ensure_ascii=False, indent=2)

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