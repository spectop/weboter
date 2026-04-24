from __future__ import annotations

from fastapi import HTTPException


def raise_http_error(exc: Exception) -> None:
    """统一异常到 HTTP 状态码的映射。"""
    if isinstance(exc, (FileNotFoundError, NotADirectoryError, ValueError)):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc
