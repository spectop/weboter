"""
weboter.app.panel
-----------------
面板认证与前端静态资源。

- auth.py                 单用户认证管理器（PBKDF2 + Cookie session）
- static/index.html       控制面板 HTML 外壳
- static/assets/*.css/js  控制面板静态样式与脚本资源
"""

from __future__ import annotations

import importlib.resources
from pathlib import PurePosixPath

from .auth import PANEL_SESSION_COOKIE, PanelAuthManager, PanelUserRecord

__all__ = [
    "PANEL_SESSION_COOKIE",
    "PanelAuthManager",
    "PanelUserRecord",
    "read_panel_html",
    "read_panel_asset",
]


def read_panel_html() -> str:
    """读取并返回控制面板 SPA 的 HTML 内容。"""
    return (
        importlib.resources.files("weboter.app.panel")
        .joinpath("static/index.html")
        .read_text(encoding="utf-8")
    )


def read_panel_asset(asset_path: str) -> bytes:
    """读取 panel 静态资源，限制在 static/assets 目录内。"""
    normalized = PurePosixPath(asset_path)
    if normalized.is_absolute() or any(part in {"", ".", ".."} for part in normalized.parts):
        raise FileNotFoundError(asset_path)
    return (
        importlib.resources.files("weboter.app.panel")
        .joinpath("static")
        .joinpath("assets")
        .joinpath(*normalized.parts)
        .read_bytes()
    )
