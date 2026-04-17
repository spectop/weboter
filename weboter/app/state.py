from dataclasses import dataclass
import json
from pathlib import Path

from weboter.app.config import load_app_config


@dataclass
class ServiceState:
    host: str
    port: int
    pid: int
    workspace_root: str
    log_path: str
    started_at: str


def default_workspace_root() -> Path:
    return load_app_config().workspace_root_path()


def default_data_root(workspace_root: Path | None = None) -> Path:
    config = load_app_config()
    if workspace_root is not None:
        candidate = Path(config.paths.data_root).expanduser()
        if not candidate.is_absolute():
            candidate = workspace_root.resolve() / candidate
        return candidate.resolve()
    return config.data_root_path()


def default_service_state_path(workspace_root: Path | None = None) -> Path:
    return default_data_root(workspace_root) / "service.json"


def load_service_state(state_path: Path | None = None, workspace_root: Path | None = None) -> ServiceState | None:
    target_path = (state_path or default_service_state_path(workspace_root)).expanduser().resolve()
    if not target_path.is_file():
        return None
    with open(target_path, "r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)
    return ServiceState(**data)