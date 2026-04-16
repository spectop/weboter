import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from weboter.app.service import ServiceState, WorkflowService


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
        execute: bool = False,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/workflow/dir",
            {
                "directory": str(directory.expanduser().resolve()),
                "name": workflow_name,
                "list": list_only,
                "execute": execute,
            },
        )