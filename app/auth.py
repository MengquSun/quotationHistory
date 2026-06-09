from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

from app import db
from app.config import get_settings


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt_text, digest_text = stored.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    expected = _hash_password(password, base64.b64decode(salt_text)).split("$", 2)[2]
    return hmac.compare_digest(expected, digest_text)


def create_user(email: str, password: str, name: str | None = None, role: str = "user") -> dict:
    db.init_db()
    with db.connect() as conn:
        existing = conn.execute("select id from users where lower(email) = lower(?)", (email,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Email is already registered.")
        cur = conn.execute(
            "insert into users (name, email, password_hash, role) values (?, ?, ?, ?)",
            (name or email.split("@")[0], email, _hash_password(password), role),
        )
        user_id = int(cur.lastrowid)
        row = conn.execute("select id, name, email, role, created_at from users where id = ?", (user_id,)).fetchone()
    return db.row_to_dict(row) or {}


def authenticate(email: str, password: str) -> dict | None:
    db.init_db()
    with db.connect() as conn:
        row = conn.execute("select * from users where lower(email) = lower(?)", (email,)).fetchone()
    user = db.row_to_dict(row)
    if not user or not user.get("password_hash"):
        return None
    if not _verify_password(password, str(user["password_hash"])):
        return None
    user.pop("password_hash", None)
    return user


def issue_token(user_id: int) -> str:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=settings.token_ttl_minutes)).isoformat()
    with db.connect() as conn:
        conn.execute("insert into auth_tokens (user_id, token_hash, expires_at) values (?, ?, ?)", (user_id, token_hash, expires_at))
    return token


def user_for_token(token: str) -> dict | None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as conn:
        row = conn.execute(
            """
            select u.id, u.name, u.email, u.role, u.created_at
            from auth_tokens t
            join users u on u.id = t.user_id
            where t.token_hash = ? and t.expires_at > ? and t.revoked_at is null
            """,
            (token_hash, now),
        ).fetchone()
    return db.row_to_dict(row)


def current_user(authorization: str | None = Header(default=None), x_user_role: str | None = Header(default=None)) -> dict | None:
    if authorization and authorization.lower().startswith("bearer "):
        return user_for_token(authorization.split(" ", 1)[1].strip())
    if x_user_role:
        return {"id": None, "name": "legacy-header", "email": None, "role": x_user_role}
    return None


def require_role(user: dict | None, role: str = "admin") -> None:
    if not user or user.get("role") != role:
        raise HTTPException(status_code=403, detail=f"{role.title()} role required.")
