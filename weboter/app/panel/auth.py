from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
from typing import Any


# Cookie 名称，供 server 中间件和路由共用
PANEL_SESSION_COOKIE = "weboter_panel_session"


@dataclass
class PanelUserRecord:
    username: str
    password_salt: str
    password_hash: str
    iterations: int
    needs_reset: bool
    updated_at: str


class PanelAuthManager:
    """面板单用户认证管理器。负责密码存储（PBKDF2）、会话令牌管理。"""

    def __init__(self, data_root: Path):
        self._data_root = data_root
        self._user_file = data_root / "panel_user.json"
        self._session_ttl = timedelta(hours=12)
        self._sessions: dict[str, dict[str, str]] = {}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(tz=timezone.utc)

    @staticmethod
    def _now_str() -> str:
        return PanelAuthManager._now().isoformat(timespec="seconds")

    @staticmethod
    def _hash_password(password: str, salt: bytes, iterations: int) -> str:
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return digest.hex()

    def _load_user(self) -> PanelUserRecord:
        if not self._user_file.is_file():
            return self._bootstrap_default_user()
        data = json.loads(self._user_file.read_text(encoding="utf-8"))
        return PanelUserRecord(
            username=str(data.get("username", "")).strip(),
            password_salt=str(data.get("password_salt", "")).strip(),
            password_hash=str(data.get("password_hash", "")).strip(),
            iterations=int(data.get("iterations", 240000)),
            needs_reset=bool(data.get("needs_reset", False)),
            updated_at=str(data.get("updated_at", self._now_str())),
        )

    def _save_user(self, record: PanelUserRecord) -> None:
        self._data_root.mkdir(parents=True, exist_ok=True)
        self._user_file.write_text(
            json.dumps(
                {
                    "username": record.username,
                    "password_salt": record.password_salt,
                    "password_hash": record.password_hash,
                    "iterations": record.iterations,
                    "needs_reset": record.needs_reset,
                    "updated_at": record.updated_at,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _bootstrap_default_user(self) -> PanelUserRecord:
        # 初始账号仅用于本地首次进入面板，建议立刻通过 CLI 重置。
        return self.reset_credentials("admin", "admin", needs_reset=True)

    def reset_credentials(self, username: str, password: str, needs_reset: bool = False) -> PanelUserRecord:
        normalized_username = username.strip()
        if not normalized_username:
            raise ValueError("用户名不能为空")
        if len(password) < 4:
            raise ValueError("密码长度至少为 4")
        salt = secrets.token_bytes(16)
        iterations = 240000
        password_hash = self._hash_password(password, salt, iterations)
        record = PanelUserRecord(
            username=normalized_username,
            password_salt=salt.hex(),
            password_hash=password_hash,
            iterations=iterations,
            needs_reset=bool(needs_reset),
            updated_at=self._now_str(),
        )
        self._save_user(record)
        self._sessions.clear()
        return record

    def summary(self) -> dict[str, Any]:
        record = self._load_user()
        return {
            "username": record.username,
            "needs_reset": record.needs_reset,
            "updated_at": record.updated_at,
        }

    def verify_credentials(self, username: str, password: str) -> bool:
        record = self._load_user()
        if username.strip() != record.username:
            return False
        salt = bytes.fromhex(record.password_salt)
        expected = record.password_hash
        actual = self._hash_password(password, salt, record.iterations)
        return hmac.compare_digest(expected, actual)

    def create_session(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = self._now() + self._session_ttl
        self._sessions[token] = {
            "username": username,
            "expires_at": expires_at.isoformat(timespec="seconds"),
        }
        return token

    def resolve_session(self, token: str) -> str | None:
        if not token:
            return None
        entry = self._sessions.get(token)
        if entry is None:
            return None
        expires_at = datetime.fromisoformat(entry["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= self._now():
            self._sessions.pop(token, None)
            return None
        return entry["username"]

    def revoke_session(self, token: str) -> None:
        if token:
            self._sessions.pop(token, None)
