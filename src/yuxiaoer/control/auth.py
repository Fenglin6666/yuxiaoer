"""控制台账号：PBKDF2 密码哈希 + 按店授权。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yuxiaoer.core import config


@dataclass
class ControlUser:
    username: str
    password_hash: str
    role: str = "owner"          # admin | owner
    shops: list[str] = field(default_factory=list)  # ["*"] 表示全部

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "role": self.role,
            "shops": list(self.shops),
        }

    def can_access(self, shop_id: str) -> bool:
        return self.role == "admin" or "*" in self.shops or shop_id in self.shops


def hash_password(password: str, *, iterations: int = 200_000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(got, expected)
    except (ValueError, TypeError):
        return False


class UserRegistry:
    def __init__(self, path: Path | None = None):
        self.path = path or Path(
            os.getenv("YUXIAOER_CONTROL_DIR", config.PROJECT_ROOT / "data" / "control")
        ) / "users.json"
        self._users: dict[str, ControlUser] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            password = os.getenv("YUXIAOER_CONTROL_PASSWORD", "admin")
            self._users = {
                "admin": ControlUser("admin", hash_password(password), "admin", ["*"])
            }
            self.save()
            return
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows = []
        self._users = {}
        for row in rows:
            try:
                user = ControlUser(**row)
                self._users[user.username] = user
            except TypeError:
                continue

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([user.to_dict() for user in self._users.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def authenticate(self, username: str, password: str) -> ControlUser | None:
        user = self._users.get(username or "")
        if user and verify_password(password, user.password_hash):
            return user
        return None

    def list(self) -> list[ControlUser]:
        return sorted(self._users.values(), key=lambda user: user.username)

    def get(self, username: str) -> ControlUser | None:
        return self._users.get(username)

    def upsert(self, username: str, password: str | None, role: str, shops: list[str]) -> ControlUser:
        username = (username or "").strip()[:40]
        if not username:
            raise ValueError("用户名不能为空")
        role = "admin" if role == "admin" else "owner"
        current = self._users.get(username)
        if password:
            password_hash = hash_password(password)
        elif current:
            password_hash = current.password_hash
        else:
            raise ValueError("新用户必须设置密码")
        user = ControlUser(username, password_hash, role, ["*"] if role == "admin" else shops)
        self._users[username] = user
        self.save()
        return user

    def delete(self, username: str) -> bool:
        if username == "admin":
            raise ValueError("不能删除 admin")
        if username not in self._users:
            return False
        self._users.pop(username)
        self.save()
        return True
