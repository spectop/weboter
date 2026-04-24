from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from fastapi import FastAPI, Query


def register_task_routes(app: FastAPI, *, task_manager, raise_http_error: Callable[[Exception], None]) -> None:
    @app.get("/tasks", tags=["task"])
    def list_tasks(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
        return {
            "items": [asdict(task) for task in task_manager.list_tasks(limit)],
            "queue": task_manager.queue_status(),
        }

    @app.get("/tasks/{task_id}", tags=["task"])
    def get_task(task_id: str) -> dict[str, Any]:
        try:
            return asdict(task_manager.get_task(task_id))
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/tasks/{task_id}/logs", tags=["task"])
    def get_task_logs(task_id: str, lines: int = Query(default=200, ge=1, le=2000)) -> dict[str, Any]:
        try:
            return task_manager.read_task_log(task_id, lines)
        except Exception as exc:
            raise_http_error(exc)
