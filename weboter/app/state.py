from dataclasses import dataclass
import json
import os
from pathlib import Path


@dataclass
class ServiceState:
    host: str
    port: int
    pid: int
    workspace_root: str
    log_path: str
    started_at: str


def default_workspace_root() -> Path:
    return Path(os.environ.get("WEBOTER_HOME", Path(__file__).resolve().parents[2])).resolve()


def default_data_root(workspace_root: Path | None = None) -> Path:
    return (workspace_root or default_workspace_root()).resolve() / ".weboter"


def default_service_state_path(workspace_root: Path | None = None) -> Path:
    return default_data_root(workspace_root) / "service.json"


def load_service_state(state_path: Path | None = None, workspace_root: Path | None = None) -> ServiceState | None:
    target_path = (state_path or default_service_state_path(workspace_root)).expanduser().resolve()
    if not target_path.is_file():
        return None
    with open(target_path, "r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)
    return ServiceState(**data)