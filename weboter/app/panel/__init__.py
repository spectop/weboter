"""
weboter.app.panel
-----------------
面板认证与前端静态资源。

- auth.py           单用户认证管理器（PBKDF2 + Cookie session）
- static/index.html 控制面板 SPA（HTML / CSS / JS 一体化单文件）
"""

from __future__ import annotations

import importlib.resources

from .auth import PANEL_SESSION_COOKIE, PanelAuthManager, PanelUserRecord

__all__ = ["PANEL_SESSION_COOKIE", "PanelAuthManager", "PanelUserRecord", "read_panel_html"]


def read_panel_html() -> str:
    """读取并返回控制面板 SPA 的 HTML 内容。"""
    return (
        importlib.resources.files("weboter.app.panel")
        .joinpath("static/index.html")
        .read_text(encoding="utf-8")
    )
