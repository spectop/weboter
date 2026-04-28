import asyncio
from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path
from pathlib import PurePosixPath
import shutil
import secrets
from typing import Any
from zipfile import ZipFile

from weboter.app.config import AppConfig, load_app_config
from weboter.app.env_store import ManagedEnvStore
from weboter.app.state import ServiceState, default_workspace_root
from weboter.core.plugin_loader import ensure_plugins_initialized, get_plugin_snapshot, refresh_plugins
from weboter.core.engine.action_manager import action_manager
from weboter.core.engine.control_manager import control_manager
from weboter.core.engine.excutor import Executor
from weboter.core.workflow_io import WorkflowReader, WorkflowWriter
from weboter.public.model import Flow, Node, NodeOutputConfig


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
        ensure_plugins_initialized(self.config)

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

    def _parse_node_output(self, payload: Any, *, context: str) -> NodeOutputConfig:
        if not isinstance(payload, dict):
            raise ValueError(f"{context} output must be an object")
        src = str(payload.get("src", "")).strip()
        if not src:
            raise ValueError(f"{context} output.src is required")
        return NodeOutputConfig(
            src=src,
            name=str(payload.get("name", "") or ""),
            pos=str(payload.get("pos", "flow") or "flow"),
            cvt=str(payload.get("cvt", "") or ""),
        )

    def _parse_node(self, payload: Any, *, context: str) -> Node:
        if not isinstance(payload, dict):
            raise ValueError(f"{context} must be an object")
        node_id = str(payload.get("node_id", "")).strip()
        if not node_id:
            raise ValueError(f"{context}.node_id is required")

        inputs = payload.get("inputs") or {}
        if not isinstance(inputs, dict):
            raise ValueError(f"{context}.inputs must be an object")
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError(f"{context}.params must be an object")
        outputs_raw = payload.get("outputs") or []
        if not isinstance(outputs_raw, list):
            raise ValueError(f"{context}.outputs must be an array")

        outputs = [
            self._parse_node_output(item, context=f"{context}.outputs[{index}]")
            for index, item in enumerate(outputs_raw)
        ]

        return Node(
            node_id=node_id,
            name=str(payload.get("name", "") or ""),
            description=str(payload.get("description", "") or ""),
            action=str(payload.get("action", "") or ""),
            inputs=inputs,
            outputs=outputs,
            control=str(payload.get("control", "") or ""),
            params=params,
            log=str(payload.get("log", "short") or "short"),
        )

    def _parse_flow(self, payload: Any, *, context: str) -> Flow:
        if not isinstance(payload, dict):
            raise ValueError(f"{context} must be an object")

        flow_id = str(payload.get("flow_id", "")).strip()
        if not flow_id:
            raise ValueError(f"{context}.flow_id is required")

        nodes_raw = payload.get("nodes") or []
        if not isinstance(nodes_raw, list):
            raise ValueError(f"{context}.nodes must be an array")
        nodes = [self._parse_node(item, context=f"{context}.nodes[{index}]") for index, item in enumerate(nodes_raw)]

        node_ids: set[str] = set()
        for node in nodes:
            if node.node_id in node_ids:
                raise ValueError(f"{context}.nodes contains duplicate node_id: {node.node_id}")
            node_ids.add(node.node_id)

        sub_flows_raw = payload.get("sub_flows") or []
        if not isinstance(sub_flows_raw, list):
            raise ValueError(f"{context}.sub_flows must be an array")
        sub_flows = [
            self._parse_flow(item, context=f"{context}.sub_flows[{index}]")
            for index, item in enumerate(sub_flows_raw)
        ]

        return Flow(
            flow_id=flow_id,
            name=str(payload.get("name", "") or ""),
            description=str(payload.get("description", "") or ""),
            start_node_id=str(payload.get("start_node_id", "") or ""),
            nodes=nodes,
            sub_flows=sub_flows,
            log=str(payload.get("log", "short") or "short"),
        )

    def update_workflow(self, directory: Path, workflow_name: str, flow_data: dict[str, Any]) -> Path:
        resolution = self.resolve_from_directory(directory, workflow_name)
        flow = self._parse_flow(flow_data, context="flow")
        WorkflowWriter.to_json(flow, resolution.source_path, indent=2)
        return resolution.source_path

    def run_workflow(self, workflow_path: Path, logger: logging.Logger | None = None, hooks: Any | None = None) -> Path:
        ensure_plugins_initialized(self.config)
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
        ensure_plugins_initialized(self.config)
        items = [self._summarize_contract_item(item) for item in action_manager.list_actions()]
        return {"items": items}

    def get_action(self, full_name: str) -> dict[str, Any] | None:
        ensure_plugins_initialized(self.config)
        item = action_manager.describe_action(full_name)
        if item is None:
            return None
        return {"action": item}

    def list_controls(self) -> dict[str, Any]:
        ensure_plugins_initialized(self.config)
        items = [self._summarize_contract_item(item) for item in control_manager.list_controls()]
        return {"items": items}

    def get_control(self, full_name: str) -> dict[str, Any] | None:
        ensure_plugins_initialized(self.config)
        item = control_manager.describe_control(full_name)
        if item is None:
            return None
        return {"control": item}

    def list_plugins(self) -> dict[str, Any]:
        ensure_plugins_initialized(self.config)
        snapshot = get_plugin_snapshot(self.config)
        source_map = {
            item["package"]: {
                "source": item.get("source") or "",
                "module": item.get("module") or "",
            }
            for item in snapshot.get("loaded") or []
            if item.get("package")
        }

        plugins: dict[str, dict[str, Any]] = {}
        for action in action_manager.list_actions():
            plugin = plugins.setdefault(
                action["package"],
                self._make_plugin_summary(action["package"], source_map.get(action["package"])),
            )
            plugin["actions"].append(action)
        for control in control_manager.list_controls():
            plugin = plugins.setdefault(
                control["package"],
                self._make_plugin_summary(control["package"], source_map.get(control["package"])),
            )
            plugin["controls"].append(control)

        items = []
        for package_name, plugin in sorted(plugins.items()):
            plugin["action_count"] = len(plugin["actions"])
            plugin["control_count"] = len(plugin["controls"])
            plugin["description"] = self._plugin_description(plugin)
            items.append(plugin)

        return {
            "plugin_root": snapshot.get("plugin_root") or str(self.config.plugin_root_path()),
            "items": items,
            "loaded": snapshot.get("loaded") or [],
            "errors": snapshot.get("errors") or [],
        }

    def refresh_plugins(self) -> dict[str, Any]:
        return refresh_plugins(self.config)

    def install_plugin_archive(self, source: Path, replace: bool = True) -> dict[str, Any]:
        source_path = source.expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Plugin archive not found: {source_path}")
        if source_path.suffix.lower() != ".zip":
            raise ValueError("插件上传目前仅支持 .zip 压缩包")

        plugin_root = self.config.plugin_root_path()
        plugin_root.mkdir(parents=True, exist_ok=True)

        with ZipFile(source_path) as archive:
            members = [name for name in archive.namelist() if name and not name.endswith("/")]
            if not members:
                raise ValueError("插件压缩包为空")

            top_levels = {PurePosixPath(name).parts[0] for name in members if PurePosixPath(name).parts}
            has_root_init = any(PurePosixPath(name).name == "__init__.py" and len(PurePosixPath(name).parts) == 1 for name in members)
            if len(top_levels) == 1 and not has_root_init:
                archive_root = next(iter(top_levels))
                init_name = f"{archive_root}/__init__.py"
                if init_name not in members:
                    raise ValueError("插件压缩包必须包含顶层插件目录及 __init__.py")
                target_dir = plugin_root / archive_root
                strip_parts = 1
            else:
                if "__init__.py" not in members:
                    raise ValueError("插件压缩包必须在根目录包含 __init__.py，或提供单个顶层插件目录")
                target_dir = plugin_root / source_path.stem
                strip_parts = 0

            if target_dir.exists():
                if not replace:
                    raise FileExistsError(f"插件目录已存在: {target_dir.name}")
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)

            for member in members:
                pure_path = PurePosixPath(member)
                parts = pure_path.parts[strip_parts:]
                if not parts:
                    continue
                relative_path = Path(*parts)
                destination = (target_dir / relative_path).resolve()
                if target_dir.resolve() not in destination.parents and destination != target_dir.resolve():
                    raise ValueError("插件压缩包包含非法路径")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, open(destination, "wb") as dst:
                    shutil.copyfileobj(src, dst)

        refresh_result = self.refresh_plugins()
        return {
            "uploaded": str(target_dir),
            "plugin_root": str(plugin_root),
            "refresh": refresh_result,
        }

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

    def _make_plugin_summary(self, package_name: str, source_info: dict[str, Any] | None) -> dict[str, Any]:
        source_info = source_info or {}
        source = source_info.get("source") or ("builtin" if package_name == "builtin" else "unknown")
        return {
            "package": package_name,
            "source": source,
            "module": source_info.get("module") or ("weboter.builtin" if package_name == "builtin" else ""),
            "description": "",
            "actions": [],
            "controls": [],
            "action_count": 0,
            "control_count": 0,
        }

    def _plugin_description(self, plugin: dict[str, Any]) -> str:
        for item in plugin.get("actions") or []:
            description = (item.get("description") or "").strip()
            if description:
                return description
        for item in plugin.get("controls") or []:
            description = (item.get("description") or "").strip()
            if description:
                return description
        return ""

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