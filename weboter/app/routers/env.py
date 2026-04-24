from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI, Query

from weboter.app.schemas import EnvImportRequest, EnvSetRequest


def register_env_routes(app: FastAPI, *, service, raise_http_error: Callable[[Exception], None]) -> None:
    @app.get("/env", tags=["env"])
    def list_env(group: str | None = Query(default=None)) -> dict[str, Any]:
        try:
            return service.list_env(group)
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/env/tree", tags=["env"])
    def env_tree(group: str | None = Query(default=None)) -> dict[str, Any]:
        try:
            return service.env_tree(group)
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/env/{name:path}", tags=["env"])
    def get_env(name: str, reveal: bool = Query(default=False)) -> dict[str, Any]:
        try:
            return service.get_env(name, reveal=reveal)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/env", tags=["env"])
    def set_env(payload: EnvSetRequest) -> dict[str, Any]:
        try:
            return service.set_env(payload.name, payload.value)
        except Exception as exc:
            raise_http_error(exc)

    @app.delete("/env/{name:path}", tags=["env"])
    def delete_env(name: str) -> dict[str, Any]:
        try:
            return service.delete_env(name)
        except Exception as exc:
            raise_http_error(exc)

    @app.post("/env/import", tags=["env"])
    def import_env(payload: EnvImportRequest) -> dict[str, Any]:
        try:
            return service.import_env(payload.data, replace=payload.replace)
        except Exception as exc:
            raise_http_error(exc)

    @app.get("/env/export", tags=["env"])
    def export_env(group: str | None = Query(default=None), reveal: bool = Query(default=False)) -> dict[str, Any]:
        try:
            return service.export_env(group, reveal=reveal)
        except Exception as exc:
            raise_http_error(exc)
