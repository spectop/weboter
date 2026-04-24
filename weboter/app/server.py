from __future__ import annotations

from dataclasses import asdict
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse
import uvicorn

from weboter.app.client import ServiceClientError, WorkflowServiceClient
from weboter.app.http_utils import raise_http_error
from weboter.app.panel import PANEL_SESSION_COOKIE, PanelAuthManager
from weboter.app.routers.catalog import register_catalog_routes
from weboter.app.routers.env import register_env_routes
from weboter.app.routers.panel import register_panel_routes
from weboter.app.routers.service import register_service_routes
from weboter.app.routers.sessions import register_session_routes
from weboter.app.routers.tasks import register_task_routes
from weboter.app.routers.workflows import register_workflow_routes
from weboter.app.session import ExecutionSessionManager
from weboter.app.service import WorkflowService
from weboter.app.task_manager import TaskManager


DEFAULT_SERVICE_HOST = "127.0.0.1"
DEFAULT_SERVICE_PORT = 0


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _process_group_exists(pgid: int) -> bool:
    if not hasattr(os, "killpg"):
        return _process_exists(pgid)
    try:
        os.killpg(pgid, 0)
    except OSError:
        return False
    return True


def _read_process_cmdline(pid: int) -> list[str]:
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    if not cmdline_path.is_file():
        return []
    raw = cmdline_path.read_bytes().split(b"\0")
    return [item.decode("utf-8", errors="ignore") for item in raw if item]


def _read_process_stat(pid: int) -> dict[str, Any] | None:
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.is_file():
        return None
    content = stat_path.read_text(encoding="utf-8").strip()
    end_comm = content.rfind(")")
    if end_comm < 0:
        return None
    prefix = content[: end_comm + 1]
    suffix = content[end_comm + 2 :].split()
    if len(suffix) < 3:
        return None
    return {
        "pid": pid,
        "comm": prefix[prefix.find("(") + 1 : -1],
        "state": suffix[0],
        "ppid": int(suffix[1]),
        "pgid": int(suffix[2]),
    }


def _classify_process(cmdline: list[str], comm: str) -> str:
    joined = " ".join(cmdline) if cmdline else comm
    lowered = joined.lower()
    if "playwright" in lowered:
        return "playwright"
    if "chrome" in lowered or "chromium" in lowered or "firefox" in lowered or "webkit" in lowered:
        return "browser"
    if "weboter" in lowered:
        return "service"
    return "other"


def list_service_processes(workflow_service: WorkflowService | None = None) -> dict[str, Any]:
    workflow_service = workflow_service or WorkflowService()
    state = workflow_service.read_service_state()
    if state is None:
        raise RuntimeError("service 未启动")
    if not _process_exists(state.pid):
        workflow_service.remove_service_state()
        raise RuntimeError("service 状态文件已过期")

    processes: list[dict[str, Any]] = []
    proc_root = Path("/proc")
    for entry in sorted(proc_root.iterdir(), key=lambda item: int(item.name) if item.name.isdigit() else 0):
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        stat = _read_process_stat(pid)
        if stat is None or stat["pgid"] != state.pid:
            continue
        cmdline = _read_process_cmdline(pid)
        processes.append(
            {
                "pid": pid,
                "ppid": stat["ppid"],
                "pgid": stat["pgid"],
                "state": stat["state"],
                "comm": stat["comm"],
                "kind": _classify_process(cmdline, stat["comm"]),
                "cmdline": cmdline,
            }
        )

    return {
        "service": {
            "pid": state.pid,
            "host": state.host,
            "port": state.port,
        },
        "items": processes,
    }


def _is_expected_service_process(pid: int) -> bool:
    cmdline = _read_process_cmdline(pid)
    if not cmdline:
        return True
    joined = " ".join(cmdline)
    return "weboter" in joined and "service" in joined and "--foreground" in joined


def _signal_service_process_tree(pid: int, sig: int) -> None:
    if hasattr(os, "killpg"):
        os.killpg(pid, sig)
        return
    os.kill(pid, sig)


def _wait_for_service_process_exit(pid: int, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    exists = _process_group_exists if hasattr(os, "killpg") else _process_exists
    while time.time() < deadline:
        if not exists(pid):
            return True
        time.sleep(0.2)
    return not exists(pid)


def _consume_secret_notice(workflow_service: WorkflowService) -> dict[str, str] | None:
    if not workflow_service.should_announce_secrets():
        return None
    secrets_summary = workflow_service.get_secret_summary()
    if not secrets_summary:
        return None
    workflow_service.mark_secrets_announced()
    return secrets_summary


def _configure_service_logger(workflow_service: WorkflowService) -> logging.Logger:
    logger = logging.getLogger("weboter.service")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(
        isinstance(handler, logging.FileHandler)
        and getattr(handler, "baseFilename", None) == str(workflow_service.service_log_path)
        for handler in logger.handlers
    ):
        handler = logging.FileHandler(workflow_service.service_log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)
    return logger


def create_app(workflow_service: WorkflowService | None = None) -> FastAPI:
    service = workflow_service or WorkflowService()
    system_logger = _configure_service_logger(service)
    session_manager = ExecutionSessionManager(service.data_root / "sessions", system_logger)
    task_manager = TaskManager(service, system_logger, session_manager=session_manager)
    panel_auth = PanelAuthManager(service.data_root)
    # 启动时确保存在单用户账号（默认 admin/admin，可通过 CLI 重置）。
    panel_auth.summary()
    api_token = service.get_api_token() or ""

    app = FastAPI(
        title="Weboter Local Service",
        version="0.1.20",
        summary="Weboter 本地 workflow 执行服务",
    )
    app.state.workflow_service = service
    app.state.system_logger = system_logger
    app.state.task_manager = task_manager
    app.state.session_manager = session_manager
    app.state.panel_auth = panel_auth

    def _request_source(request: Request) -> str:
        caller = request.headers.get("X-Weboter-Caller", "").strip()
        if caller:
            return caller
        user_agent = request.headers.get("User-Agent", "").strip()
        if user_agent:
            return user_agent
        return request.client.host if request.client else "unknown"

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if not api_token:
            return await call_next(request)

        path = request.url.path
        public_paths = {"/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
        if path in public_paths or path.startswith("/docs") or path == "/panel" or path.startswith("/panel/"):
            return await call_next(request)

        provided = request.headers.get("X-Weboter-Token", "")
        if provided != api_token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    @app.middleware("http")
    async def panel_session_middleware(request: Request, call_next):
        path = request.url.path
        if not path.startswith("/panel/api"):
            return await call_next(request)
        if path in {"/panel/api/login", "/panel/api/status"}:
            return await call_next(request)

        token = request.cookies.get(PANEL_SESSION_COOKIE, "")
        username = panel_auth.resolve_session(token)
        if not username:
            return JSONResponse({"error": "panel unauthorized"}, status_code=401)
        request.state.panel_user = username
        return await call_next(request)

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        started_at = time.time()
        source = _request_source(request)
        system_logger.info(
            "HTTP request start source=%s method=%s path=%s query=%s",
            source,
            request.method,
            request.url.path,
            request.url.query,
        )
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.time() - started_at) * 1000)
            system_logger.exception(
                "HTTP request failed source=%s method=%s path=%s duration_ms=%s",
                source,
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
        duration_ms = int((time.time() - started_at) * 1000)
        system_logger.info(
            "HTTP request end source=%s method=%s path=%s status=%s duration_ms=%s",
            source,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    register_panel_routes(
        app,
        service=service,
        task_manager=task_manager,
        session_manager=session_manager,
        panel_auth=panel_auth,
        raise_http_error=raise_http_error,
    )
    register_service_routes(
        app,
        service=service,
        list_service_processes=list_service_processes,
        raise_http_error=raise_http_error,
    )
    register_env_routes(app, service=service, raise_http_error=raise_http_error)
    register_catalog_routes(app, service=service, raise_http_error=raise_http_error)
    register_task_routes(app, task_manager=task_manager, raise_http_error=raise_http_error)
    register_session_routes(app, session_manager=session_manager, raise_http_error=raise_http_error)
    register_workflow_routes(
        app,
        service=service,
        task_manager=task_manager,
        system_logger=system_logger,
        raise_http_error=raise_http_error,
    )

    return app


def _create_server_socket(host: str, port: int) -> socket.socket:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen(2048)
    return server_socket


def serve_foreground(host: str, port: int, workflow_service: WorkflowService | None = None) -> int:
    workflow_service = workflow_service or WorkflowService()
    _configure_service_logger(workflow_service).info("service 前台启动中")
    app = create_app(workflow_service)
    server_socket = _create_server_socket(host, port)
    actual_host, actual_port = server_socket.getsockname()[:2]
    workflow_service.write_service_state(workflow_service.build_service_state(actual_host, actual_port, os.getpid()))
    if os.environ.get("WEBOTER_SUPPRESS_SECRET_NOTICE", "").strip() != "1":
        secret_notice = _consume_secret_notice(workflow_service)
        if secret_notice:
            print("Weboter secrets (首次启动提示，仅显示一次):", flush=True)
            for key, value in secret_notice.items():
                print(f"- {key}: {value}", flush=True)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=actual_host,
            port=actual_port,
            access_log=False,
            log_level="warning",
        )
    )

    def _shutdown_handler(signum: int, frame: Any) -> None:
        server.should_exit = True

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    try:
        server.run(sockets=[server_socket])
    finally:
        workflow_service.remove_service_state()
        server_socket.close()
    return 0


def start_background_service(
    host: str,
    port: int,
    workflow_service: WorkflowService | None = None,
) -> dict[str, Any]:
    workflow_service = workflow_service or WorkflowService()
    client = WorkflowServiceClient(workflow_service)

    try:
        health = client.health()
        service = health.get("service") or {}
        return {
            "status": "already-running",
            "pid": health.get("pid"),
            "host": service.get("host"),
            "port": service.get("port"),
        }
    except ServiceClientError:
        workflow_service.remove_service_state()

    workflow_service.data_root.mkdir(parents=True, exist_ok=True)
    child_env = os.environ.copy()
    child_env["WEBOTER_SUPPRESS_SECRET_NOTICE"] = "1"
    with open(workflow_service.service_log_path, "a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "weboter",
                "service",
                "start",
                "--foreground",
                "--host",
                host,
                "--port",
                str(port),
            ],
            cwd=str(workflow_service.workspace_root),
            stdout=log_file,
            stderr=log_file,
            env=child_env,
            start_new_session=True,
        )

    deadline = time.time() + 10
    while time.time() < deadline:
        if process.poll() is not None:
            break
        time.sleep(0.2)
        try:
            client.health()
            state = workflow_service.read_service_state()
            return {
                "status": "started",
                "pid": state.pid if state else process.pid,
                "host": state.host if state else host,
                "port": state.port if state else port,
                "secret_notice": _consume_secret_notice(workflow_service),
            }
        except ServiceClientError:
            continue

    raise RuntimeError(f"service 启动失败，请检查日志: {workflow_service.service_log_path}")


def stop_background_service(workflow_service: WorkflowService | None = None) -> dict[str, Any]:
    workflow_service = workflow_service or WorkflowService()
    state = workflow_service.read_service_state()
    if state is None:
        raise RuntimeError("service 未启动")

    if not _process_exists(state.pid):
        workflow_service.remove_service_state()
        return {"status": "stopped", "pid": state.pid, "host": state.host, "port": state.port}

    if not _is_expected_service_process(state.pid):
        workflow_service.remove_service_state()
        raise RuntimeError(f"service 状态文件中的 pid 已被其他进程占用: {state.pid}")

    _signal_service_process_tree(state.pid, signal.SIGTERM)
    if _wait_for_service_process_exit(state.pid, 5):
        workflow_service.remove_service_state()
        return {"status": "stopped", "pid": state.pid, "host": state.host, "port": state.port}

    _signal_service_process_tree(state.pid, signal.SIGKILL)
    if _wait_for_service_process_exit(state.pid, 2):
        workflow_service.remove_service_state()
        return {"status": "killed", "pid": state.pid, "host": state.host, "port": state.port}

    return {"status": "stop-requested", "pid": state.pid, "host": state.host, "port": state.port}


def restart_background_service(
    host: str,
    port: int,
    workflow_service: WorkflowService | None = None,
) -> dict[str, Any]:
    workflow_service = workflow_service or WorkflowService()
    previous: dict[str, Any] | None = None
    state = workflow_service.read_service_state()
    if state is not None:
        previous = stop_background_service(workflow_service)
    started = start_background_service(host, port, workflow_service)
    started["status"] = "restarted" if previous is not None else started.get("status", "started")
    if previous is not None:
        started["previous"] = previous
    return started


def service_status(workflow_service: WorkflowService | None = None) -> dict[str, Any]:
    workflow_service = workflow_service or WorkflowService()
    client = WorkflowServiceClient(workflow_service)
    health = client.health()
    service = health.get("service") or {}
    return {
        "status": "running",
        "pid": health.get("pid"),
        "host": service.get("host"),
        "port": service.get("port"),
        "workspace_root": health.get("workspace_root"),
        "api_url": f"http://{service.get('host')}:{service.get('port')}",
        "openapi_url": f"http://{service.get('host')}:{service.get('port')}/openapi.json",
        "docs_url": f"http://{service.get('host')}:{service.get('port')}/docs",
        "service_log_path": str(workflow_service.service_log_path),
        "config_path": str(workflow_service.config.config_path) if workflow_service.config.config_path else None,
        "auth_enabled": workflow_service.config.service.auth.enabled,
    }
