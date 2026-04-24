from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI

from weboter.app.schemas import WorkflowDirectoryRequest, WorkflowUploadRequest


def register_workflow_routes(
    app: FastAPI,
    *,
    service,
    task_manager,
    system_logger,
    raise_http_error: Callable[[Exception], None],
) -> None:
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
            raise_http_error(exc)

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
            raise_http_error(exc)
