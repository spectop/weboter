from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import tempfile
from typing import Any, Callable

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from starlette.responses import HTMLResponse

from weboter.app.panel import PANEL_SESSION_COOKIE, PanelAuthManager, read_panel_asset, read_panel_html
from weboter.app.schemas import EnvSetRequest, PanelLoginRequest, PanelWorkflowSaveRequest
from weboter.core.workflow_io import WorkflowReader


def register_panel_routes(
    app: FastAPI,
    *,
    service,
    task_manager,
    session_manager,
    panel_auth: PanelAuthManager,
    raise_http_error: Callable[[Exception], None],
) -> None:
    asset_media_types = {
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
    }

    @app.get("/panel", tags=["panel"])
    def panel_page() -> HTMLResponse:
        return HTMLResponse(read_panel_html())

    @app.get("/panel/assets/{asset_path:path}", tags=["panel"])
    def panel_asset(asset_path: str) -> Response:
        try:
            suffix = Path(asset_path).suffix.lower()
            media_type = asset_media_types.get(suffix, "application/octet-stream")
            return Response(read_panel_asset(asset_path), media_type=media_type)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"panel asset not found: {asset_path}") from exc

    @app.get("/panel/api/status", tags=["panel"])
    def panel_status() -> dict[str, Any]:
        return panel_auth.summary()

    @app.post("/panel/api/login", tags=["panel"])
    def panel_login(payload: PanelLoginRequest, response: Response) -> dict[str, Any]:
        if not panel_auth.verify_credentials(payload.username, payload.password):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        token = panel_auth.create_session(payload.username.strip())
        response.set_cookie(
            key=PANEL_SESSION_COOKIE,
            value=token,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=12 * 3600,
        )
        return {"ok": True, "username": payload.username.strip()}

    @app.post("/panel/api/logout", tags=["panel"])
    def panel_logout(request: Request, response: Response) -> dict[str, Any]:
        token = request.cookies.get(PANEL_SESSION_COOKIE, "")
        panel_auth.revoke_session(token)
        response.delete_cookie(PANEL_SESSION_COOKIE)
        return {"ok": True}

    @app.get("/panel/api/me", tags=["panel"])
    def panel_me(request: Request) -> dict[str, Any]:
        info = panel_auth.summary()
        return {
            "username": getattr(request.state, "panel_user", None),
            "needs_reset": info.get("needs_reset", False),
            "updated_at": info.get("updated_at"),
        }

    @app.get("/panel/api/env", tags=["panel"])
    def panel_env_list(group: str | None = Query(default=None)) -> dict[str, Any]:
        try:
            return service.list_env(group)
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/panel/api/env/tree", tags=["panel"])
    def panel_env_tree(group: str | None = Query(default=None)) -> dict[str, Any]:
        try:
            return service.env_tree(group)
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/panel/api/env/{name:path}", tags=["panel"])
    def panel_env_get(name: str, reveal: bool = Query(default=False)) -> dict[str, Any]:
        try:
            return service.get_env(name, reveal=reveal)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/panel/api/env", tags=["panel"])
    def panel_env_set(payload: EnvSetRequest) -> dict[str, Any]:
        try:
            return service.set_env(payload.name, payload.value)
        except Exception as exc:
            raise_http_error(exc)

    @app.delete("/panel/api/env/{name:path}", tags=["panel"])
    def panel_env_delete(name: str) -> dict[str, Any]:
        try:
            return service.delete_env(name)
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/panel/api/plugins", tags=["panel"])
    def panel_plugins() -> dict[str, Any]:
        try:
            return service.list_plugins()
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/panel/api/plugins/refresh", tags=["panel"])
    def panel_plugins_refresh() -> dict[str, Any]:
        try:
            return service.refresh_plugins()
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/panel/api/plugins/upload", tags=["panel"])
    async def panel_plugins_upload(file: UploadFile = File(...)) -> dict[str, Any]:
        suffix = Path(file.filename or "plugin.zip").suffix or ".zip"
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_path = Path(tmp.name)
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    tmp.write(chunk)
            return service.install_plugin_archive(temp_path)
        except Exception as exc:
            raise_http_error(exc)
        finally:
            await file.close()
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    @app.get("/panel/api/workflows", tags=["panel"])
    def panel_workflow_list() -> dict[str, Any]:
        try:
            items = service.list_directory_workflows(service.workflow_store)
            workflows: list[dict[str, str]] = []
            for workflow_name in items:
                display_name = workflow_name
                try:
                    resolution = service.resolve_from_directory(service.workflow_store, workflow_name)
                    flow = WorkflowReader.from_json(resolution.source_path)
                    if flow.name:
                        display_name = flow.name
                except Exception:
                    # 某个 workflow 读取失败时，列表仍然返回其逻辑名，避免整个页面不可用。
                    display_name = workflow_name
                workflows.append({"workflow": workflow_name, "name": display_name})
            return {
                "directory": str(service.workflow_store),
                "items": items,
                "workflows": workflows,
            }
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/panel/api/workflows/{workflow_name:path}", tags=["panel"])
    def panel_workflow_detail(workflow_name: str) -> dict[str, Any]:
        try:
            resolution = service.resolve_from_directory(service.workflow_store, workflow_name)
            flow = WorkflowReader.from_json(resolution.source_path)
            return {
                "name": workflow_name,
                "path": str(resolution.source_path),
                "flow": asdict(flow),
            }
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/panel/api/workflows/{workflow_name:path}/create-task", tags=["panel"])
    def panel_workflow_create_task(workflow_name: str) -> dict[str, Any]:
        try:
            resolution = service.resolve_from_directory(service.workflow_store, workflow_name)
            task = task_manager.submit(
                resolution.source_path,
                trigger="panel_workflow",
                pause_before_start=False,
                breakpoints=[],
            )
            return {
                "workflow": workflow_name,
                "resolved": str(resolution.source_path),
                "task": asdict(task),
            }
        except Exception as exc:
            raise_http_error(exc)

    @app.put("/panel/api/workflows/{workflow_name:path}", tags=["panel"])
    def panel_workflow_update(workflow_name: str, payload: PanelWorkflowSaveRequest) -> dict[str, Any]:
        try:
            saved_path = service.update_workflow(service.workflow_store, workflow_name, payload.flow)
            flow = WorkflowReader.from_json(saved_path)
            return {
                "workflow": workflow_name,
                "path": str(saved_path),
                "updated": True,
                "flow": asdict(flow),
            }
        except Exception as exc:
            raise_http_error(exc)

    @app.delete("/panel/api/workflows/{workflow_name:path}", tags=["panel"])
    def panel_workflow_delete(workflow_name: str) -> dict[str, Any]:
        try:
            deleted_path = service.delete_workflow(service.workflow_store, workflow_name)
            return {
                "workflow": workflow_name,
                "deleted": str(deleted_path),
            }
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/panel/api/overview", tags=["panel"])
    def panel_overview() -> dict[str, Any]:
        recent_tasks = [asdict(item) for item in task_manager.list_tasks(10)]
        recent_sessions = [asdict(item) for item in session_manager.list_sessions(10)]
        service_state_data = service.read_service_state()
        return {
            "service": {
                "status": "ok",
                "pid": os.getpid(),
                "state": asdict(service_state_data) if service_state_data else None,
            },
            "task_queue": task_manager.queue_status(),
            "tasks": recent_tasks,
            "sessions": recent_sessions,
            "session_count": len(recent_sessions),
        }

    @app.get("/panel/api/tasks", tags=["panel"])
    def panel_tasks(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
        return {
            "items": [asdict(item) for item in task_manager.list_tasks(limit)],
            "queue": task_manager.queue_status(),
        }

    @app.get("/panel/api/tasks/{task_id}", tags=["panel"])
    def panel_task_detail(task_id: str) -> dict[str, Any]:
        try:
            return asdict(task_manager.get_task(task_id))
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/panel/api/tasks/{task_id}/logs", tags=["panel"])
    def panel_task_logs(task_id: str, lines: int = Query(default=200, ge=1, le=2000)) -> dict[str, Any]:
        try:
            return task_manager.read_task_log(task_id, lines)
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/panel/api/sessions", tags=["panel"])
    def panel_sessions(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
        return {
            "items": [asdict(item) for item in session_manager.list_sessions(limit)],
        }

    @app.get("/panel/api/sessions/{session_id}", tags=["panel"])
    def panel_session_detail(session_id: str) -> dict[str, Any]:
        try:
            return asdict(session_manager.get_session(session_id))
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/panel/api/sessions/{session_id}/pause", tags=["panel"])
    def panel_session_pause(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.request_pause(session_id)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/panel/api/sessions/{session_id}/resume", tags=["panel"])
    def panel_session_resume(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.resume(session_id)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/panel/api/sessions/{session_id}/abort", tags=["panel"])
    def panel_session_abort(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.abort(session_id)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/panel/api/sessions/{session_id}/interrupt", tags=["panel"])
    def panel_session_interrupt(session_id: str, reason: str = Query(default="interrupt_next")) -> dict[str, Any]:
        try:
            return session_manager.request_interrupt(session_id, reason)
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/panel/{panel_path:path}", tags=["panel"])
    def panel_subpage(panel_path: str) -> HTMLResponse:
        if panel_path.startswith("api/") or panel_path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="panel route not found")
        return HTMLResponse(read_panel_html())
