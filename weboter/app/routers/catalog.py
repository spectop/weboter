from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, HTTPException


def register_catalog_routes(app: FastAPI, *, service, raise_http_error: Callable[[Exception], None]) -> None:
    @app.get("/catalog/actions", tags=["catalog"])
    def list_actions() -> dict:
        return service.list_actions()

    @app.get("/catalog/actions/{full_name:path}", tags=["catalog"])
    def get_action(full_name: str) -> dict:
        item = service.get_action(full_name)
        if item is None:
            raise HTTPException(status_code=404, detail=f"action not found: {full_name}")
        return item

    @app.get("/catalog/controls", tags=["catalog"])
    def list_controls() -> dict:
        return service.list_controls()

    @app.get("/catalog/controls/{full_name:path}", tags=["catalog"])
    def get_control(full_name: str) -> dict:
        item = service.get_control(full_name)
        if item is None:
            raise HTTPException(status_code=404, detail=f"control not found: {full_name}")
        return item

    @app.post("/catalog/refresh", tags=["catalog"])
    def refresh_catalog() -> dict:
        try:
            return service.refresh_plugins()
        except Exception as exc:
            raise_http_error(exc)
