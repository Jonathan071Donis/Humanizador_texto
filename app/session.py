"""
Anonymous, no-account browser session tracking.

There are no user accounts or logins in this app. To let the dashboard
show "what did I just process" without a database, each browser gets a
random session id (a cookie, not a login) the first time it visits, and
recent processing history is kept in memory keyed by that id. Restarting
the server or clearing cookies wipes the history - this is intentional
(dev/demo mode, no database).
"""
from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional

from fastapi import Cookie, Response

SESSION_COOKIE_NAME = "wm_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
MAX_HISTORY_PER_SESSION = 50

# session_id -> list of {"filename": str, "findings": int, "ts": float}
SESSION_HISTORY: Dict[str, List[dict]] = {}


def get_or_create_session_id(
    response: Response,
    wm_session: Optional[str] = Cookie(default=None),
) -> str:
    """FastAPI dependency: returns the current session id, creating and
    setting a cookie for it if the visitor doesn't have one yet."""
    session_id = wm_session
    if not session_id:
        session_id = uuid.uuid4().hex
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_id,
            httponly=True,
            samesite="lax",
            max_age=SESSION_TTL_SECONDS,
        )
    return session_id


def record_history(session_id: str, filename: str, findings: int) -> None:
    entry = {"filename": filename, "findings": findings, "ts": time.time()}
    history = SESSION_HISTORY.setdefault(session_id, [])
    history.append(entry)
    del history[:-MAX_HISTORY_PER_SESSION]


def get_history(session_id: str) -> List[dict]:
    return SESSION_HISTORY.get(session_id, [])
