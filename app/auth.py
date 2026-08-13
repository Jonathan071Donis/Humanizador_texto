"""
Deliberately simple, no-database auth.

- Users live in a plain dict in process memory. Restarting the server
  wipes all accounts - this is intentional (dev/demo mode), per spec.
- Sessions are stateless JWTs (HS256) signed with SECRET_KEY from the
  environment, so no server-side session store is needed either.
- An optional JSON file backing store can be enabled with
  USERS_JSON_FILE for light persistence across restarts (still no DB).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

import bcrypt
import jwt
from fastapi import Cookie, Header, HTTPException, status

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me-in-production")
ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", str(60 * 60 * 8)))  # 8h
USERS_JSON_FILE = os.getenv("USERS_JSON_FILE")  # optional, e.g. "users.json"


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
USERS: Dict[str, Dict] = {}          # username -> {"password_hash": str, "created_at": float}
USER_HISTORY: Dict[str, list] = {}   # username -> list of processed-file summaries
USER_PREFS: Dict[str, Dict] = {}     # username -> {"favorite_keywords": [...]}


def _load_users_from_disk() -> None:
    if not USERS_JSON_FILE:
        return
    p = Path(USERS_JSON_FILE)
    if p.exists():
        try:
            USERS.update(json.loads(p.read_text()))
        except Exception:
            pass


def _persist_users_to_disk() -> None:
    if not USERS_JSON_FILE:
        return
    try:
        Path(USERS_JSON_FILE).write_text(json.dumps(USERS))
    except Exception:
        pass


_load_users_from_disk()


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

def create_user(username: str, password: str) -> None:
    username = username.strip()
    if username in USERS:
        raise ValueError("Username already exists")
    USERS[username] = {
        "password_hash": _hash_password(password),
        "created_at": time.time(),
    }
    USER_HISTORY[username] = []
    USER_PREFS[username] = {"favorite_keywords": []}
    _persist_users_to_disk()


def verify_user(username: str, password: str) -> bool:
    user = USERS.get(username)
    if not user:
        return False
    return _verify_password(password, user["password_hash"])


# ---------------------------------------------------------------------------
# JWT session tokens
# ---------------------------------------------------------------------------

def create_access_token(username: str) -> str:
    payload = {"sub": username, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def get_current_user(
    access_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
) -> str:
    """Dependency used by protected routes. Accepts the session either as an
    httpOnly cookie ('access_token') or a Bearer header, so it works for
    both the server-rendered pages and pure API/JS clients."""
    token = access_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    username = decode_access_token(token)
    if not username or username not in USERS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    return username


def get_current_user_optional(
    access_token: Optional[str] = Cookie(default=None),
) -> Optional[str]:
    if not access_token:
        return None
    username = decode_access_token(access_token)
    if username and username in USERS:
        return username
    return None
