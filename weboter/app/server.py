from __future__ import annotations

from dataclasses import asdict
import logging
import os
import socket
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse
import uvicorn

from weboter.app.client import ServiceClientError, WorkflowServiceClient
from weboter.app.config import load_app_config
from weboter.app.session import ExecutionSessionManager
from weboter.app.service import WorkflowService
from weboter.app.task_manager import TERMINAL_TASK_STATUSES, TaskManager


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
    prefix = content[:end_comm + 1]
    suffix = content[end_comm + 2:].split()
    if len(suffix) < 3:
        return None
    return {
        "pid": pid,
        "comm": prefix[prefix.find("(") + 1:-1],
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


class WorkflowUploadRequest(BaseModel):
    path: str
    execute: bool = False
    pause_before_start: bool = False
    breakpoints: List[Dict[str, Any]] = Field(default_factory=list)


class WorkflowDirectoryRequest(BaseModel):
    directory: str
    name: str | None = None
    list: bool = False
    delete: bool = False
    execute: bool = False
    pause_before_start: bool = False
    breakpoints: List[Dict[str, Any]] = Field(default_factory=list)


class SessionSetContextRequest(BaseModel):
    key: str
    value: Any


class SessionRuntimeValueRequest(BaseModel):
    key: str


class SessionJumpRequest(BaseModel):
    node_id: str


class SessionInterruptRequest(BaseModel):
    reason: str = "interrupt_next"


class SessionConfigureBreakpointsRequest(BaseModel):
    breakpoints: list[dict[str, Any]]
    replace: bool = True


class SessionClearBreakpointsRequest(BaseModel):
    breakpoint_ids: list[str] | None = None


class SessionSnapshotDetailSectionsRequest(BaseModel):
    sections: List[str] = Field(default_factory=list)


class SessionPatchNodeRequest(BaseModel):
    node_id: str
    patch: dict[str, Any]


class SessionAddNodeRequest(BaseModel):
    node: dict[str, Any]


class SessionExportWorkflowRequest(BaseModel):
    path: str


class SessionPageEvaluateRequest(BaseModel):
    script: str
    arg: Any | None = None


class SessionPageScriptRequest(BaseModel):
    code: str
    arg: Any | None = None
    timeout_ms: int = 5000


class SessionPageGotoRequest(BaseModel):
    url: str


class SessionPageClickRequest(BaseModel):
    locator: str
    timeout: int = 5000


class SessionPageFillRequest(BaseModel):
    locator: str
    value: str
    timeout: int = 5000


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
    session_manager = ExecutionSessionManager(service.data_root / "sessions", system_logger)
    task_manager = TaskManager(service, system_logger, session_manager=session_manager)
    api_token = service.get_api_token() or ""
    app = FastAPI(
        title="Weboter Local Service",
        version="0.1.11",
        summary="Weboter 本地 workflow 执行服务",
    )
    app.state.workflow_service = service
    app.state.system_logger = system_logger
    app.state.task_manager = task_manager
    app.state.session_manager = session_manager

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
        if path in public_paths or path.startswith("/docs"):
            return await call_next(request)

        provided = request.headers.get("X-Weboter-Token", "")
        if provided != api_token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
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

    @app.get("/service/processes", tags=["service"])
    def service_processes() -> dict[str, Any]:
        try:
            return list_service_processes(service)
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/catalog/actions", tags=["catalog"])
    def list_actions() -> dict[str, Any]:
        return service.list_actions()

    @app.get("/catalog/actions/{full_name:path}", tags=["catalog"])
    def get_action(full_name: str) -> dict[str, Any]:
        item = service.get_action(full_name)
        if item is None:
            raise HTTPException(status_code=404, detail=f"action not found: {full_name}")
        return item

    @app.get("/catalog/controls", tags=["catalog"])
    def list_controls() -> dict[str, Any]:
        return service.list_controls()

    @app.get("/catalog/controls/{full_name:path}", tags=["catalog"])
    def get_control(full_name: str) -> dict[str, Any]:
        item = service.get_control(full_name)
        if item is None:
            raise HTTPException(status_code=404, detail=f"control not found: {full_name}")
        return item

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

    @app.get("/sessions", tags=["session"])
    def list_sessions(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
        return {"items": [asdict(item) for item in session_manager.list_sessions(limit)]}

    @app.get("/sessions/{session_id}", tags=["session"])
    def get_session(session_id: str) -> dict[str, Any]:
        try:
            return asdict(session_manager.get_session(session_id))
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/sessions/{session_id}/snapshots", tags=["session"])
    def get_session_snapshots(session_id: str, limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
        try:
            return {"items": session_manager.get_snapshots(session_id, limit)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/sessions/{session_id}/snapshots/{snapshot_index}", tags=["session"])
    def get_session_snapshot_detail(
        session_id: str,
        snapshot_index: int,
        sections: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            requested_sections = []
            if sections:
                requested_sections = [item for item in sections.split(",") if item.strip()]
            return session_manager.get_snapshot_detail(session_id, snapshot_index, requested_sections)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/pause", tags=["session"])
    def pause_session(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.request_pause(session_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/interrupt", tags=["session"])
    def interrupt_session(session_id: str, payload: SessionInterruptRequest) -> dict[str, Any]:
        try:
            return session_manager.request_interrupt(session_id, payload.reason)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/resume", tags=["session"])
    def resume_session(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.resume(session_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/abort", tags=["session"])
    def abort_session(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.abort(session_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/context", tags=["session"])
    def session_set_context(session_id: str, payload: SessionSetContextRequest) -> dict[str, Any]:
        try:
            return session_manager.set_context(session_id, payload.key, payload.value)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/jump", tags=["session"])
    def session_jump(session_id: str, payload: SessionJumpRequest) -> dict[str, Any]:
        try:
            return session_manager.jump_to_node(session_id, payload.node_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/patch-node", tags=["session"])
    def session_patch_node(session_id: str, payload: SessionPatchNodeRequest) -> dict[str, Any]:
        try:
            return session_manager.patch_node(session_id, payload.node_id, payload.patch)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/add-node", tags=["session"])
    def session_add_node(session_id: str, payload: SessionAddNodeRequest) -> dict[str, Any]:
        try:
            return session_manager.add_node(session_id, payload.node)
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/sessions/{session_id}/workflow", tags=["session"])
    def session_workflow(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.get_workflow(session_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/sessions/{session_id}/workflow/node/{node_id}", tags=["session"])
    def session_workflow_node(session_id: str, node_id: str) -> dict[str, Any]:
        try:
            return session_manager.get_workflow_node(session_id, node_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/sessions/{session_id}/runtime", tags=["session"])
    def session_runtime_value(session_id: str, key: str = Query(...)) -> dict[str, Any]:
        try:
            return session_manager.get_runtime_value(session_id, key)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/breakpoints", tags=["session"])
    def session_breakpoints(session_id: str, payload: SessionConfigureBreakpointsRequest) -> dict[str, Any]:
        try:
            return session_manager.configure_breakpoints(session_id, payload.breakpoints, replace=payload.replace)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/breakpoints/clear", tags=["session"])
    def session_clear_breakpoints(session_id: str, payload: SessionClearBreakpointsRequest) -> dict[str, Any]:
        try:
            return session_manager.clear_breakpoints(session_id, payload.breakpoint_ids)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/export-workflow", tags=["session"])
    def session_export_workflow(session_id: str, payload: SessionExportWorkflowRequest) -> dict[str, Any]:
        try:
            return session_manager.export_workflow(session_id, payload.path)
        except Exception as exc:
            _raise_http_error(exc)

    @app.get("/sessions/{session_id}/page", tags=["session"])
    def session_page_snapshot(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.page_snapshot(session_id)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/page/evaluate", tags=["session"])
    def session_page_evaluate(session_id: str, payload: SessionPageEvaluateRequest) -> Any:
        try:
            return {"result": session_manager.page_evaluate(session_id, payload.script, payload.arg)}
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/page/script", tags=["session"])
    def session_page_script(session_id: str, payload: SessionPageScriptRequest) -> dict[str, Any]:
        try:
            return session_manager.page_run_script(session_id, payload.code, payload.arg, payload.timeout_ms)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/page/goto", tags=["session"])
    def session_page_goto(session_id: str, payload: SessionPageGotoRequest) -> dict[str, Any]:
        try:
            return session_manager.page_goto(session_id, payload.url)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/page/click", tags=["session"])
    def session_page_click(session_id: str, payload: SessionPageClickRequest) -> dict[str, Any]:
        try:
            return session_manager.page_click(session_id, payload.locator, payload.timeout)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/sessions/{session_id}/page/fill", tags=["session"])
    def session_page_fill(session_id: str, payload: SessionPageFillRequest) -> dict[str, Any]:
        try:
            return session_manager.page_fill(session_id, payload.locator, payload.value, payload.timeout)
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/workflow/upload", tags=["workflow"])
    def workflow_upload(payload: WorkflowUploadRequest) -> dict[str, Any]:
        try:
            system_logger.info(
                "workflow upload path=%s execute=%s pause_before_start=%s breakpoints=%s",
                payload.path,
                payload.execute,
                payload.pause_before_start,
                len(payload.breakpoints),
            )
            if not payload.execute:
                return service.handle_upload_request(Path(payload.path), False)
            resolution = service.upload_workflow(Path(payload.path))
            task = task_manager.submit(
                resolution.source_path,
                trigger="upload",
                pause_before_start=payload.pause_before_start,
                breakpoints=payload.breakpoints,
            )
            return {
                "uploaded": str(resolution.managed_path or resolution.source_path),
                "task": asdict(task),
            }
        except Exception as exc:
            _raise_http_error(exc)

    @app.post("/workflow/dir", tags=["workflow"])
    def workflow_dir(payload: WorkflowDirectoryRequest) -> dict[str, Any]:
        try:
            system_logger.info(
                "workflow dir directory=%s name=%s list=%s delete=%s execute=%s pause_before_start=%s breakpoints=%s",
                payload.directory,
                payload.name,
                payload.list,
                payload.delete,
                payload.execute,
                payload.pause_before_start,
                len(payload.breakpoints),
            )
            if payload.list:
                return service.handle_directory_request(Path(payload.directory), payload.name, True, False, False)
            if payload.delete:
                return service.handle_directory_request(Path(payload.directory), payload.name, False, True, False)
            if not payload.execute:
                return service.handle_directory_request(Path(payload.directory), payload.name, False, False, False)
            resolution = service.resolve_from_directory(Path(payload.directory), payload.name)
            task = task_manager.submit(
                resolution.source_path,
                trigger="directory",
                pause_before_start=payload.pause_before_start,
                breakpoints=payload.breakpoints,
            )
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