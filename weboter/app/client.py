import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from weboter.app.service import ServiceState, WorkflowService


TERMINAL_TASK_STATUSES = {"succeeded", "failed"}


class ServiceClientError(RuntimeError):
    pass


class WorkflowServiceClient:
    def __init__(self, workflow_service: WorkflowService | None = None):
        self.workflow_service = workflow_service or WorkflowService()
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _load_state(self) -> ServiceState:
        state = self.workflow_service.read_service_state()
        if state is None:
            raise ServiceClientError("service 未启动，请先执行 `weboter serve start`")
        return state

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self._load_state()
        url = f"http://{state.host}:{state.port}{path}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self._opener.open(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                error_payload = json.loads(exc.read().decode("utf-8"))
                message = error_payload.get("error", str(exc))
            except Exception:
                message = str(exc)
            raise ServiceClientError(message) from exc
        except urllib.error.URLError as exc:
            raise ServiceClientError("service 不可用，请检查 `weboter serve status`") from exc

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def service_logs(self, lines: int = 200) -> dict[str, Any]:
        query = urllib.parse.urlencode({"lines": lines})
        return self._request("GET", f"/service/logs?{query}")

    def upload_workflow(self, source: Path, execute: bool = False) -> dict[str, Any]:
        return self._request(
            "POST",
            "/workflow/upload",
            {"path": str(source.expanduser().resolve()), "execute": execute},
        )

    def handle_directory(
        self,
        directory: Path,
        workflow_name: str | None = None,
        list_only: bool = False,
        delete: bool = False,
        execute: bool = False,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/workflow/dir",
            {
                "directory": str(directory.expanduser().resolve()),
                "name": workflow_name,
                "list": list_only,
                "delete": delete,
                "execute": execute,
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

    def wait_for_task(self, task_id: str, timeout: float | None = None, interval: float = 0.5) -> dict[str, Any]:
        deadline = None if timeout is None or timeout <= 0 else time.time() + timeout
        while True:
            task = self.get_task(task_id)
            if task.get("status") in TERMINAL_TASK_STATUSES:
                return task
            if deadline is not None and time.time() >= deadline:
                raise ServiceClientError(f"wait task timeout: {task_id}")
            time.sleep(interval)