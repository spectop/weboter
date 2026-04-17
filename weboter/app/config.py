from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_FILE_NAME = "weboter.yaml"


@dataclass
class PathsConfig:
    workspace_root: str | None = None
    data_root: str = ".weboter"
    workflow_store: str = "workflows"


@dataclass
class AuthConfig:
    enabled: bool = False
    token: str | None = None
    show_secrets_once: bool = True


@dataclass
class ServiceConfig:
    host: str = "127.0.0.1"
    port: int = 0
    auth: AuthConfig = field(default_factory=AuthConfig)


@dataclass
class MCPConfig:
    service_url: str | None = None
    profile: str = "operator"
    transport: str = "stdio"
    caller_name: str = "mcp"


@dataclass
class ClientConfig:
    api_token: str | None = None
    caller_name: str = ""
    request_timeout: float = 10.0


@dataclass
class AppConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    service: ServiceConfig = field(default_factory=ServiceConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    client: ClientConfig = field(default_factory=ClientConfig)
    config_path: Path | None = None

    def workspace_root_path(self) -> Path:
        base_dir = self.config_path.parent if self.config_path else Path(__file__).resolve().parents[2]
        raw_value = self.paths.workspace_root
        if raw_value:
            candidate = Path(raw_value).expanduser()
            if not candidate.is_absolute():
                candidate = (base_dir / candidate).resolve()
            return candidate.resolve()
        return base_dir.resolve()

    def data_root_path(self) -> Path:
        workspace_root = self.workspace_root_path()
        candidate = Path(self.paths.data_root).expanduser()
        if not candidate.is_absolute():
            candidate = workspace_root / candidate
        return candidate.resolve()

    def workflow_store_path(self) -> Path:
        data_root = self.data_root_path()
        candidate = Path(self.paths.workflow_store).expanduser()
        if not candidate.is_absolute():
            candidate = data_root / candidate
        return candidate.resolve()

    def service_secret_state_path(self) -> Path:
        return self.data_root_path() / "secrets.json"


def default_config_path() -> Path:
    configured = os.environ.get("WEBOTER_CONFIG", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    cwd_candidate = (Path.cwd() / DEFAULT_CONFIG_FILE_NAME).resolve()
    if cwd_candidate.is_file():
        return cwd_candidate

    return (Path(__file__).resolve().parents[2] / DEFAULT_CONFIG_FILE_NAME).resolve()


def _merge_dataclass(instance: Any, payload: dict[str, Any] | None) -> Any:
    if not payload:
        return instance
    for key, value in payload.items():
        if not hasattr(instance, key):
            continue
        current = getattr(instance, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _merge_dataclass(current, value)
            continue
        setattr(instance, key, value)
    return instance


def _read_env_bool(name: str) -> bool | None:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return None
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _read_env_int(name: str) -> int | None:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return None
    return int(raw_value.strip())


def _read_env_float(name: str) -> float | None:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return None
    return float(raw_value.strip())


def _apply_env_overrides(config: AppConfig) -> AppConfig:
    workspace_root = os.environ.get("WEBOTER_HOME") or os.environ.get("WEBOTER_WORKSPACE_ROOT")
    if workspace_root:
        config.paths.workspace_root = workspace_root.strip()

    data_root = os.environ.get("WEBOTER_DATA_ROOT", "").strip()
    if data_root:
        config.paths.data_root = data_root

    workflow_store = os.environ.get("WEBOTER_WORKFLOW_STORE", "").strip()
    if workflow_store:
        config.paths.workflow_store = workflow_store

    service_host = os.environ.get("WEBOTER_SERVICE_HOST", "").strip()
    if service_host:
        config.service.host = service_host

    service_port = _read_env_int("WEBOTER_SERVICE_PORT")
    if service_port is not None:
        config.service.port = service_port

    auth_enabled = _read_env_bool("WEBOTER_SERVICE_AUTH_ENABLED")
    if auth_enabled is None:
        auth_enabled = _read_env_bool("WEBOTER_API_TOKEN_ENABLED")
    if auth_enabled is not None:
        config.service.auth.enabled = auth_enabled

    api_token = os.environ.get("WEBOTER_API_TOKEN")
    if api_token is not None:
        config.service.auth.token = api_token.strip() or None
        config.client.api_token = api_token.strip() or None

    show_secrets_once = _read_env_bool("WEBOTER_SHOW_SECRETS_ONCE")
    if show_secrets_once is not None:
        config.service.auth.show_secrets_once = show_secrets_once

    service_url = os.environ.get("WEBOTER_MCP_SERVICE_URL") or os.environ.get("WEBOTER_SERVICE_URL")
    if service_url:
        config.mcp.service_url = service_url.strip()

    mcp_profile = os.environ.get("WEBOTER_MCP_PROFILE", "").strip()
    if mcp_profile:
        config.mcp.profile = mcp_profile

    mcp_transport = os.environ.get("WEBOTER_MCP_TRANSPORT", "").strip()
    if mcp_transport:
        config.mcp.transport = mcp_transport

    mcp_caller_name = os.environ.get("WEBOTER_MCP_CALLER_NAME", "").strip()
    if mcp_caller_name:
        config.mcp.caller_name = mcp_caller_name

    client_caller_name = os.environ.get("WEBOTER_CALLER_NAME", "").strip()
    if client_caller_name:
        config.client.caller_name = client_caller_name

    client_timeout = _read_env_float("WEBOTER_CLIENT_TIMEOUT")
    if client_timeout is not None:
        config.client.request_timeout = client_timeout

    return config


def load_app_config(config_path: Path | None = None) -> AppConfig:
    target_path = (config_path or default_config_path()).expanduser().resolve()
    config = AppConfig(config_path=target_path)
    if not target_path.is_file():
        return _apply_env_overrides(config)

    with open(target_path, "r", encoding="utf-8") as file_obj:
        payload = yaml.safe_load(file_obj) or {}

    _merge_dataclass(config, payload)
    config.config_path = target_path
    return _apply_env_overrides(config)