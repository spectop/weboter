from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query


def _tail_file(path: Path, lines: int) -> str:
    if not path.is_file():
        return ""
    content = path.read_text(encoding="utf-8")
    return "\n".join(content.splitlines()[-lines:])


def register_service_routes(
    app: FastAPI,
    *,
    service,
    list_service_processes: Callable[[Any | None], dict[str, Any]],
    raise_http_error: Callable[[Exception], None],
) -> None:
    @app.get("/health", tags=["service"])
    def health() -> dict[str, Any]:
        state = service.read_service_state()
        return {
            "status": "ok",
            "pid": __import__("os").getpid(),
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
            raise_http_error(exc)
