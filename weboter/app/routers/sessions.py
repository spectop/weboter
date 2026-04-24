from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from fastapi import FastAPI, Query

from weboter.app.schemas import (
    SessionAddNodeRequest,
    SessionClearBreakpointsRequest,
    SessionConfigureBreakpointsRequest,
    SessionExportWorkflowRequest,
    SessionInterruptRequest,
    SessionJumpRequest,
    SessionPageClickRequest,
    SessionPageEvaluateRequest,
    SessionPageFillRequest,
    SessionPageGotoRequest,
    SessionPageScriptRequest,
    SessionPatchNodeRequest,
    SessionRunNodeRequest,
    SessionSetContextRequest,
)


def register_session_routes(app: FastAPI, *, session_manager, raise_http_error: Callable[[Exception], None]) -> None:
    @app.get("/sessions", tags=["session"])
    def list_sessions(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
        return {"items": [asdict(item) for item in session_manager.list_sessions(limit)]}

    @app.get("/sessions/{session_id}", tags=["session"])
    def get_session(session_id: str) -> dict[str, Any]:
        try:
            return asdict(session_manager.get_session(session_id))
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/sessions/{session_id}/snapshots", tags=["session"])
    def get_session_snapshots(session_id: str, limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
        try:
            return {"items": session_manager.get_snapshots(session_id, limit)}
        except Exception as exc:
            raise_http_error(exc)

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
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/pause", tags=["session"])
    def pause_session(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.request_pause(session_id)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/interrupt", tags=["session"])
    def interrupt_session(session_id: str, payload: SessionInterruptRequest) -> dict[str, Any]:
        try:
            return session_manager.request_interrupt(session_id, payload.reason)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/resume", tags=["session"])
    def resume_session(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.resume(session_id)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/abort", tags=["session"])
    def abort_session(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.abort(session_id)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/context", tags=["session"])
    def session_set_context(session_id: str, payload: SessionSetContextRequest) -> dict[str, Any]:
        try:
            return session_manager.set_context(session_id, payload.key, payload.value)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/jump", tags=["session"])
    def session_jump(session_id: str, payload: SessionJumpRequest) -> dict[str, Any]:
        try:
            return session_manager.jump_to_node(session_id, payload.node_id)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/patch-node", tags=["session"])
    def session_patch_node(session_id: str, payload: SessionPatchNodeRequest) -> dict[str, Any]:
        try:
            return session_manager.patch_node(session_id, payload.node_id, payload.patch)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/add-node", tags=["session"])
    def session_add_node(session_id: str, payload: SessionAddNodeRequest) -> dict[str, Any]:
        try:
            return session_manager.add_node(session_id, payload.node)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/run-node", tags=["session"])
    def session_run_node(session_id: str, payload: SessionRunNodeRequest) -> dict[str, Any]:
        try:
            return session_manager.run_temporary_node(session_id, payload.node, jump_to_node_id=payload.jump_to_node_id)
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/sessions/{session_id}/workflow", tags=["session"])
    def session_workflow(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.get_workflow(session_id)
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/sessions/{session_id}/workflow/node/{node_id}", tags=["session"])
    def session_workflow_node(session_id: str, node_id: str) -> dict[str, Any]:
        try:
            return session_manager.get_workflow_node(session_id, node_id)
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/sessions/{session_id}/runtime", tags=["session"])
    def session_runtime_value(session_id: str, key: str = Query(...)) -> dict[str, Any]:
        try:
            return session_manager.get_runtime_value(session_id, key)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/breakpoints", tags=["session"])
    def session_breakpoints(session_id: str, payload: SessionConfigureBreakpointsRequest) -> dict[str, Any]:
        try:
            return session_manager.configure_breakpoints(session_id, payload.breakpoints, replace=payload.replace)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/breakpoints/clear", tags=["session"])
    def session_clear_breakpoints(session_id: str, payload: SessionClearBreakpointsRequest) -> dict[str, Any]:
        try:
            return session_manager.clear_breakpoints(session_id, payload.breakpoint_ids)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/export-workflow", tags=["session"])
    def session_export_workflow(session_id: str, payload: SessionExportWorkflowRequest) -> dict[str, Any]:
        try:
            return session_manager.export_workflow(session_id, payload.path)
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/sessions/{session_id}/page", tags=["session"])
    def session_page_snapshot(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.page_snapshot(session_id)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/page/evaluate", tags=["session"])
    def session_page_evaluate(session_id: str, payload: SessionPageEvaluateRequest) -> Any:
        try:
            return {"result": session_manager.page_evaluate(session_id, payload.script, payload.arg)}
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/page/script", tags=["session"])
    def session_page_script(session_id: str, payload: SessionPageScriptRequest) -> dict[str, Any]:
        try:
            return session_manager.page_run_script(session_id, payload.code, payload.arg, payload.timeout_ms)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/page/goto", tags=["session"])
    def session_page_goto(session_id: str, payload: SessionPageGotoRequest) -> dict[str, Any]:
        try:
            return session_manager.page_goto(session_id, payload.url)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/page/click", tags=["session"])
    def session_page_click(session_id: str, payload: SessionPageClickRequest) -> dict[str, Any]:
        try:
            return session_manager.page_click(session_id, payload.locator, payload.timeout)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/{session_id}/page/fill", tags=["session"])
    def session_page_fill(session_id: str, payload: SessionPageFillRequest) -> dict[str, Any]:
        try:
            return session_manager.page_fill(session_id, payload.locator, payload.value, payload.timeout)
        except Exception as exc:
            raise_http_error(exc)

    @app.delete("/sessions/{session_id}", tags=["session"])
    def session_delete(session_id: str) -> dict[str, Any]:
        try:
            return session_manager.delete_session(session_id)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/sessions/cleanup", tags=["session"])
    def session_cleanup(payload: dict[str, Any] = {}) -> dict[str, Any]:
        try:
            return session_manager.cleanup_sessions(
                statuses=payload.get("statuses"),
                max_age_hours=payload.get("max_age_hours"),
                limit=int(payload.get("limit") or 100),
            )
        except Exception as exc:
            raise_http_error(exc)
