from dataclasses import asdict
import logging
import os
import socket
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import uvicorn

from weboter.app.client import ServiceClientError, WorkflowServiceClient
from weboter.app.service import WorkflowService
from weboter.app.task_manager import TERMINAL_TASK_STATUSES, TaskManager


DEFAULT_SERVICE_HOST = "127.0.0.1"
DEFAULT_SERVICE_PORT = 0


class WorkflowUploadRequest(BaseModel):
    path: str
    execute: bool = False


class WorkflowDirectoryRequest(BaseModel):
    directory: str
    name: str | None = None
    list: bool = False
    execute: bool = False


def _configure_service_logger(workflow_service: WorkflowService) -> logging.Logger:
    logger = logging.getLogger("weboter.service")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", None) == str(workflow_service.service_log_path) for handler in logger.handlers):
        handler = logging.FileHandler(workflow_service.service_log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)
    return logger


def _tail_file(path: Path, lines: int) -> str:
    if not path.is_file():
        return ""
    content = path.read_text(encoding="utf-8")
    return "\n".join(content.splitlines()[-lines:])


def create_app(workflow_service: WorkflowService | None = None) -> FastAPI:
    service = workflow_service or WorkflowService()
    system_logger = _configure_service_logger(service)
    task_manager = TaskManager(service, system_logger)
    app = FastAPI(
        title="Weboter Local Service",
        version="0.1.0",
        summary="Weboter 本地 workflow 执行服务",
    )
    app.state.workflow_service = service
    app.state.system_logger = system_logger
    app.state.task_manager = task_manager

    def _raise_http_error(exc: Exception) -> None:
        if isinstance(exc, (FileNotFoundError, NotADirectoryError, ValueError)):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/health", tags=["service"])
    def health() -> dict[str, Any]:
        state = service.read_service_state()
        return {
            "status": "ok",
            "pid": os.getpid(),
            "workspace_root": str(service.workspace_root),
            "service": asdict(state) if state else None,
        }

    @app.get("/service/state", tags=["service"])
    def service_state() -> dict[str, Any]:
        state = service.read_service_state()
        if state is None:
            raise HTTPException(status_code=503, detail="service 状态不可用")
        return asdict(state)

    @app.get("/service/logs", tags=["service"])
    def service_logs(lines: int = Query(default=200, ge=1, le=2000)) -> dict[str, Any]:
        return {
            "log_path": str(service.service_log_path),
            "content": _tail_file(service.service_log_path, lines),
        }

    @app.get("/tasks", tags=["task"])
    def list_tasks(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
        return {"items": [asdict(task) for task in task_manager.list_tasks(limit)]}

    @app.get("/tasks/{task_id}", tags=["task"])
    def get_task(task_id: str) -> dict[str, Any]:
        try:
            return asdict(task_manager.get_task(task_id))
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/tasks/{task_id}/logs", tags=["task"])
    def get_task_logs(task_id: str, lines: int = Query(default=200, ge=1, le=2000)) -> dict[str, Any]:
        try:
            return task_manager.read_task_log(task_id, lines)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/workflow/upload", tags=["workflow"])
    def workflow_upload(payload: WorkflowUploadRequest) -> dict[str, Any]:
        try:
            if not payload.execute:
                return service.handle_upload_request(Path(payload.path), False)
            resolution = service.upload_workflow(Path(payload.path))
            task = task_manager.submit(resolution.source_path, trigger="upload")
            return {
                "uploaded": str(resolution.managed_path or resolution.source_path),
                "task": asdict(task),
            }
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/workflow/dir", tags=["workflow"])
    def workflow_dir(payload: WorkflowDirectoryRequest) -> dict[str, Any]:
        try:
            if payload.list:
                return service.handle_directory_request(Path(payload.directory), payload.name, True, False)
            if not payload.execute:
                return service.handle_directory_request(Path(payload.directory), payload.name, False, False)
            resolution = service.resolve_from_directory(Path(payload.directory), payload.name)
            task = task_manager.submit(resolution.source_path, trigger="directory")
            return {
                "resolved": str(resolution.source_path),
                "task": asdict(task),
            }
        except Exception as exc:
            _raise_http_error(exc)

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
    with open(workflow_service.service_log_path, "a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "weboter",
                "serve",
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
            }
        except ServiceClientError:
            continue

    raise RuntimeError(f"service 启动失败，请检查日志: {workflow_service.service_log_path}")


def stop_background_service(workflow_service: WorkflowService | None = None) -> dict[str, Any]:
    workflow_service = workflow_service or WorkflowService()
    state = workflow_service.read_service_state()
    if state is None:
        raise RuntimeError("service 未启动")

    os.kill(state.pid, signal.SIGTERM)
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.kill(state.pid, 0)
        except OSError:
            workflow_service.remove_service_state()
            return {"status": "stopped", "pid": state.pid, "host": state.host, "port": state.port}
        time.sleep(0.2)

    workflow_service.remove_service_state()
    return {"status": "stop-requested", "pid": state.pid, "host": state.host, "port": state.port}


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
    }