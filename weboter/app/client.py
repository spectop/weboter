from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from weboter.app.config import load_app_config
from weboter.app.state import ServiceState, default_service_state_path, load_service_state

if TYPE_CHECKING:
    from weboter.app.service import WorkflowService


TERMINAL_TASK_STATUSES = {"succeeded", "failed"}


class ServiceClientError(RuntimeError):
    pass


class WorkflowServiceClient:
    def __init__(
        self,
        workflow_service: WorkflowService | None = None,
        base_url: str | None = None,
        api_token: str | None = None,
        caller_name: str | None = None,
        workspace_root: Path | None = None,
        state_path: Path | None = None,
    ):
        config = load_app_config()
        self.workflow_service = workflow_service
        self.base_url = base_url.rstrip("/") if base_url else None
        default_token = config.client.api_token
        if default_token is None and config.service.auth.enabled:
            if config.service.auth.token:
                default_token = config.service.auth.token
            else:
                from weboter.app.service import WorkflowService

                default_token = WorkflowService(config=config).get_api_token()
        self.api_token = api_token if api_token is not None else default_token
        self.caller_name = caller_name if caller_name is not None else config.client.caller_name
        self.state_path = (state_path or default_service_state_path(workspace_root)).expanduser().resolve()
        self.request_timeout = config.client.request_timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _serialize_service_path(self, path: Path | str) -> str:
        if self.base_url:
            if isinstance(path, Path):
                return path.as_posix()
            return path
        target = Path(path) if not isinstance(path, Path) else path
        if self.base_url:
            return str(target)
        return str(target.expanduser().resolve())

    def _load_state(self) -> ServiceState:
        if self.workflow_service is not None:
            state = self.workflow_service.read_service_state()
        else:
            state = load_service_state(self.state_path)
        if state is None:
            raise ServiceClientError("service 未启动，请先执行 `weboter service start`")
        return state

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.base_url:
            url = f"{self.base_url}{path}"
        else:
            state = self._load_state()
            url = f"http://{state.host}:{state.port}{path}"
        data = None
        headers = {}
        if self.api_token:
            headers["X-Weboter-Token"] = self.api_token
        if self.caller_name:
            headers["X-Weboter-Caller"] = self.caller_name
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self._opener.open(request, timeout=self.request_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                error_payload = json.loads(exc.read().decode("utf-8"))
                message = error_payload.get("error", str(exc))
            except Exception:
                message = str(exc)
            raise ServiceClientError(message) from exc
        except urllib.error.URLError as exc:
            raise ServiceClientError("service 不可用，请检查 `weboter service status`") from exc

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def service_logs(self, lines: int = 200) -> dict[str, Any]:
        query = urllib.parse.urlencode({"lines": lines})
        return self._request("GET", f"/service/logs?{query}")

    def service_processes(self) -> dict[str, Any]:
        return self._request("GET", "/service/processes")

    def list_env(self, group: str | None = None) -> dict[str, Any]:
        query = ""
        if group:
            query = "?" + urllib.parse.urlencode({"group": group})
        return self._request("GET", f"/env{query}")

    def get_env(self, name: str, reveal: bool = False) -> dict[str, Any]:
        query = "?" + urllib.parse.urlencode({"reveal": str(reveal).lower()})
        return self._request("GET", f"/env/{urllib.parse.quote(name, safe='')}{query}")

    def set_env(self, name: str, value: Any) -> dict[str, Any]:
        return self._request("POST", "/env", {"name": name, "value": value})

    def delete_env(self, name: str) -> dict[str, Any]:
        return self._request("DELETE", f"/env/{urllib.parse.quote(name, safe='')}")

    def env_tree(self, group: str | None = None) -> dict[str, Any]:
        query = ""
        if group:
            query = "?" + urllib.parse.urlencode({"group": group})
        return self._request("GET", f"/env/tree{query}")

    def import_env(self, payload: dict[str, Any], replace: bool = False) -> dict[str, Any]:
        return self._request("POST", "/env/import", {"data": payload, "replace": replace})

    def export_env(self, group: str | None = None, reveal: bool = False) -> dict[str, Any]:
        params = {"reveal": str(reveal).lower()}
        if group:
            params["group"] = group
        return self._request("GET", f"/env/export?{urllib.parse.urlencode(params)}")

    def service_state(self) -> dict[str, Any]:
        return self._request("GET", "/service/state")

    def list_actions(self) -> dict[str, Any]:
        return self._request("GET", "/catalog/actions")

    def get_action(self, full_name: str) -> dict[str, Any]:
        return self._request("GET", f"/catalog/actions/{urllib.parse.quote(full_name, safe='')}")

    def list_controls(self) -> dict[str, Any]:
        return self._request("GET", "/catalog/controls")

    def get_control(self, full_name: str) -> dict[str, Any]:
        return self._request("GET", f"/catalog/controls/{urllib.parse.quote(full_name, safe='')}")

    def upload_workflow(
        self,
        source: Path,
        execute: bool = False,
        pause_before_start: bool = False,
        breakpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/workflow/upload",
            {
                "path": self._serialize_service_path(source),
                "execute": execute,
                "pause_before_start": pause_before_start,
                "breakpoints": breakpoints or [],
            },
        )

    def handle_directory(
        self,
        directory: Path | str,
        workflow_name: str | None = None,
        list_only: bool = False,
        delete: bool = False,
        execute: bool = False,
        pause_before_start: bool = False,
        breakpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/workflow/dir",
            {
                "directory": self._serialize_service_path(directory),
                "name": workflow_name,
                "list": list_only,
                "delete": delete,
                "execute": execute,
                "pause_before_start": pause_before_start,
                "breakpoints": breakpoints or [],
            },
        )

    def list_tasks(self, limit: int = 20) -> dict[str, Any]:
        query = urllib.parse.urlencode({"limit": limit})
        return self._request("GET", f"/tasks?{query}")

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/tasks/{task_id}")

    def get_task_logs(self, task_id: str, lines: int = 200) -> dict[str, Any]:
        query = urllib.parse.urlencode({"lines": lines})
        return self._request("GET", f"/tasks/{task_id}/logs?{query}")

    def list_sessions(self, limit: int = 20) -> dict[str, Any]:
        query = urllib.parse.urlencode({"limit": limit})
        return self._request("GET", f"/sessions?{query}")

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/sessions/{session_id}")

    def get_session_snapshots(self, session_id: str, limit: int = 20) -> dict[str, Any]:
        query = urllib.parse.urlencode({"limit": limit})
        return self._request("GET", f"/sessions/{session_id}/snapshots?{query}")

    def get_session_snapshot_detail(
        self,
        session_id: str,
        snapshot_index: int,
        sections: list[str] | None = None,
    ) -> dict[str, Any]:
        query = ""
        if sections:
            query = "?" + urllib.parse.urlencode({"sections": ",".join(sections)})
        return self._request("GET", f"/sessions/{session_id}/snapshots/{snapshot_index}{query}")

    def pause_session(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/pause", {})

    def interrupt_session(self, session_id: str, reason: str = "interrupt_next") -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/interrupt", {"reason": reason})

    def resume_session(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/resume", {})

    def abort_session(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/abort", {})

    def set_session_context(self, session_id: str, key: str, value: Any) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/context", {"key": key, "value": value})

    def jump_session_node(self, session_id: str, node_id: str) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/jump", {"node_id": node_id})

    def patch_session_node(self, session_id: str, node_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/patch-node", {"node_id": node_id, "patch": patch})

    def add_session_node(self, session_id: str, node: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/add-node", {"node": node})

    def run_session_temporary_node(
        self,
        session_id: str,
        node: dict[str, Any],
        jump_to_node_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"node": node}
        if jump_to_node_id:
            payload["jump_to_node_id"] = jump_to_node_id
        return self._request("POST", f"/sessions/{session_id}/run-node", payload)

    def get_session_workflow(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/sessions/{session_id}/workflow")

    def get_session_workflow_node(self, session_id: str, node_id: str) -> dict[str, Any]:
        return self._request("GET", f"/sessions/{session_id}/workflow/node/{urllib.parse.quote(node_id, safe='')}")

    def get_session_runtime_value(self, session_id: str, key: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"key": key})
        return self._request("GET", f"/sessions/{session_id}/runtime?{query}")

    def configure_session_breakpoints(
        self,
        session_id: str,
        breakpoints: list[dict[str, Any]],
        replace: bool = True,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/sessions/{session_id}/breakpoints",
            {"breakpoints": breakpoints, "replace": replace},
        )

    def clear_session_breakpoints(self, session_id: str, breakpoint_ids: list[str] | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/sessions/{session_id}/breakpoints/clear",
            {"breakpoint_ids": breakpoint_ids},
        )

    def export_session_workflow(self, session_id: str, path: str) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/export-workflow", {"path": path})

    def get_session_page(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/sessions/{session_id}/page")

    def evaluate_session_page(self, session_id: str, script: str, arg: Any = None) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/page/evaluate", {"script": script, "arg": arg})

    def run_session_page_script(
        self,
        session_id: str,
        code: str,
        arg: Any = None,
        timeout_ms: int = 5000,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/sessions/{session_id}/page/script",
            {"code": code, "arg": arg, "timeout_ms": timeout_ms},
        )

    def session_page_goto(self, session_id: str, url: str) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/page/goto", {"url": url})

    def session_page_click(self, session_id: str, locator: str, timeout: int = 5000) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/page/click", {"locator": locator, "timeout": timeout})

    def session_page_fill(self, session_id: str, locator: str, value: str, timeout: int = 5000) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/page/fill", {"locator": locator, "value": value, "timeout": timeout})

    def wait_for_task(self, task_id: str, timeout: float | None = None, interval: float = 0.5) -> dict[str, Any]:
        deadline = None if timeout is None or timeout <= 0 else time.time() + timeout
        while True:
            task = self.get_task(task_id)
            if task.get("status") in TERMINAL_TASK_STATUSES:
                return task
            if deadline is not None and time.time() >= deadline:
                raise ServiceClientError(f"wait task timeout: {task_id}")
            time.sleep(interval)