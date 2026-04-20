import asyncio
from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path
import shutil
import secrets
from typing import Any

from weboter.app.config import AppConfig, load_app_config
from weboter.app.env_store import ManagedEnvStore
from weboter.app.state import ServiceState, default_workspace_root
from weboter.core.bootstrap import ensure_builtin_packages_registered
from weboter.core.engine.action_manager import action_manager
from weboter.core.engine.control_manager import control_manager
from weboter.core.engine.excutor import Executor
from weboter.core.workflow_io import WorkflowReader


@dataclass
class WorkflowResolution:
    source_path: Path
    managed_path: Path | None = None

class WorkflowService:
    def __init__(self, workspace_root: Path | None = None, config: AppConfig | None = None):
        config = config or load_app_config()
        self.config = config
        self.workspace_root = (workspace_root or config.workspace_root_path() or default_workspace_root()).resolve()
        self.data_root = config.data_root_path()
        self.workflow_store = config.workflow_store_path()
        self.workflow_store.mkdir(parents=True, exist_ok=True)
        self.service_state_path = self.data_root / "service.json"
        self.service_log_path = self.data_root / "service.log"
        self.secret_state_path = config.service_secret_state_path()
        self.env_store = ManagedEnvStore(self.data_root / "env.json")

    def _read_secret_state(self) -> dict[str, Any]:
        if not self.secret_state_path.is_file():
            return {}
        with open(self.secret_state_path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)

    def _write_secret_state(self, payload: dict[str, Any]) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        with open(self.secret_state_path, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)

    def get_api_token(self) -> str | None:
        auth_config = self.config.service.auth
        if not auth_config.enabled:
            return None
        if auth_config.token:
            return auth_config.token
        payload = self._read_secret_state()
        token = str(payload.get("api_token", "")).strip()
        if token:
            return token
        token = secrets.token_urlsafe(24)
        payload["api_token"] = token
        payload.setdefault("announced", False)
        self._write_secret_state(payload)
        return token

    def get_secret_summary(self) -> dict[str, str]:
        token = self.get_api_token()
        if not token:
            return {}
        return {"api_token": token}

    def should_announce_secrets(self) -> bool:
        auth_config = self.config.service.auth
        if not auth_config.enabled or not auth_config.show_secrets_once:
            return False
        payload = self._read_secret_state()
        return not bool(payload.get("announced"))

    def mark_secrets_announced(self) -> None:
        if not self.config.service.auth.enabled:
            return
        payload = self._read_secret_state()
        payload["announced"] = True
        if self.config.service.auth.token and not payload.get("api_token"):
            payload["api_token"] = self.config.service.auth.token
        self._write_secret_state(payload)

    def build_service_state(self, host: str, port: int, pid: int) -> ServiceState:
        from datetime import datetime

        return ServiceState(
            host=host,
            port=port,
            pid=pid,
            workspace_root=str(self.workspace_root),
            log_path=str(self.service_log_path),
            started_at=datetime.now().isoformat(timespec="seconds"),
        )

    def write_service_state(self, state: ServiceState) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        with open(self.service_state_path, "w", encoding="utf-8") as file_obj:
            json.dump(asdict(state), file_obj, ensure_ascii=False, indent=2)

    def read_service_state(self) -> ServiceState | None:
        if not self.service_state_path.is_file():
            return None
        with open(self.service_state_path, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
        return ServiceState(**data)

    def remove_service_state(self) -> None:
        if self.service_state_path.exists():
            self.service_state_path.unlink()

    def upload_workflow(self, source: Path) -> WorkflowResolution:
        source_path = source.expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Workflow file not found: {source_path}")

        destination = self.workflow_store / source_path.name
        if source_path != destination:
            shutil.copy2(source_path, destination)
        return WorkflowResolution(source_path=destination, managed_path=destination)

    def _workflow_name_from_path(self, directory: Path, workflow_path: Path) -> str:
        relative_path = workflow_path.relative_to(directory.expanduser().resolve())
        return ".".join(relative_path.with_suffix("").parts)

    def _workflow_path_from_name(self, directory: Path, workflow_name: str) -> Path:
        name_parts = [part for part in workflow_name.split(".") if part]
        if not name_parts:
            raise ValueError("Workflow name cannot be empty")
        return directory.expanduser().resolve().joinpath(*name_parts).with_suffix(".json")

    def resolve_from_directory(self, directory: Path, workflow_name: str | None = None) -> WorkflowResolution:
        directory_path = directory.expanduser().resolve()
        if not directory_path.is_dir():
            raise NotADirectoryError(f"Workflow directory not found: {directory_path}")

        if workflow_name:
            candidate = self._workflow_path_from_name(directory_path, workflow_name)
            if candidate.is_file():
                return WorkflowResolution(source_path=candidate)
            raise FileNotFoundError(f"Workflow '{workflow_name}' not found in: {directory_path}")

        json_files = sorted(directory_path.rglob("*.json"))
        if len(json_files) != 1:
            raise ValueError(
                "Directory mode requires exactly one workflow file, or use --name to choose one"
            )
        return WorkflowResolution(source_path=json_files[0])

    def list_directory_workflows(self, directory: Path) -> list[str]:
        directory_path = directory.expanduser().resolve()
        if not directory_path.is_dir():
            raise NotADirectoryError(f"Workflow directory not found: {directory_path}")
        workflow_paths = sorted(directory_path.rglob("*.json"))
        return [self._workflow_name_from_path(directory_path, workflow_path) for workflow_path in workflow_paths]

    def delete_workflow(self, directory: Path, workflow_name: str | None = None) -> Path:
        resolution = self.resolve_from_directory(directory, workflow_name)
        workflow_path = resolution.source_path
        if not workflow_path.is_file():
            raise FileNotFoundError(f"Workflow file not found: {workflow_path}")
        workflow_path.unlink()
        return workflow_path

    def run_workflow(self, workflow_path: Path, logger: logging.Logger | None = None, hooks: Any | None = None) -> Path:
        ensure_builtin_packages_registered()
        flow = WorkflowReader.from_json(workflow_path)
        executor = Executor(logger=logger, hooks=hooks, managed_env=self.env_store.export_env_mapping())
        executor.load_workflow(flow)
        asyncio.run(executor.run())
        return workflow_path

    def list_env(self, group: str | None = None) -> dict[str, Any]:
        return self.env_store.list_items(group)

    def get_env(self, name: str, reveal: bool = False) -> dict[str, Any]:
        return self.env_store.get(name, reveal=reveal)

    def set_env(self, name: str, value: Any) -> dict[str, Any]:
        return self.env_store.set(name, value)

    def delete_env(self, name: str) -> dict[str, Any]:
        return self.env_store.delete(name)

    def env_tree(self, group: str | None = None) -> dict[str, Any]:
        return self.env_store.tree(group)

    def import_env(self, payload: dict[str, Any], replace: bool = False) -> dict[str, Any]:
        return self.env_store.import_items(payload, replace=replace)

    def export_env(self, group: str | None = None, reveal: bool = False) -> dict[str, Any]:
        return self.env_store.export_items(group, reveal=reveal)

    def list_actions(self) -> dict[str, Any]:
        ensure_builtin_packages_registered()
        items = [self._summarize_contract_item(item) for item in action_manager.list_actions()]
        return {"items": items}

    def get_action(self, full_name: str) -> dict[str, Any] | None:
        ensure_builtin_packages_registered()
        item = action_manager.describe_action(full_name)
        if item is None:
            return None
        return {"action": item}

    def list_controls(self) -> dict[str, Any]:
        ensure_builtin_packages_registered()
        items = [self._summarize_contract_item(item) for item in control_manager.list_controls()]
        return {"items": items}

    def get_control(self, full_name: str) -> dict[str, Any] | None:
        ensure_builtin_packages_registered()
        item = control_manager.describe_control(full_name)
        if item is None:
            return None
        return {"control": item}

    def _summarize_contract_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": item["kind"],
            "package": item["package"],
            "name": item["name"],
            "full_name": item["full_name"],
            "description": item["description"],
            "input_count": len(item.get("inputs", [])),
            "output_count": len(item.get("outputs", [])),
        }

    def handle_upload_request(self, source: Path, execute: bool = False) -> dict[str, Any]:
        resolution = self.upload_workflow(source)
        response: dict[str, Any] = {
            "uploaded": str(resolution.managed_path or resolution.source_path),
        }
        if execute:
            self.run_workflow(resolution.source_path)
            response["executed"] = str(resolution.source_path)
        return response

    def handle_directory_request(
        self,
        directory: Path,
        workflow_name: str | None = None,
        list_only: bool = False,
        delete: bool = False,
        execute: bool = False,
    ) -> dict[str, Any]:
        if list_only:
            workflows = self.list_directory_workflows(directory)
            return {"items": workflows}

        if delete:
            deleted_path = self.delete_workflow(directory, workflow_name)
            return {"deleted": str(deleted_path)}

        resolution = self.resolve_from_directory(directory, workflow_name)
        response: dict[str, Any] = {"resolved": str(resolution.source_path)}
        if execute:
            self.run_workflow(resolution.source_path)
            response["executed"] = str(resolution.source_path)
        return response