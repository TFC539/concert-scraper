from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, UserSession


PBKDF2_ITERATIONS = 320000
SESSION_TTL_HOURS = 24 * 14


def hash_password(password: str) -> str:
    password_bytes = str(password or "").encode("utf-8")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password_bytes, salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = str(encoded_hash or "").split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    try:
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
    except ValueError:
        return False

    derived = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected_digest)


def _extract_bearer_token(request: Request) -> str:
    header_value = request.headers.get("authorization", "")
    if not header_value.lower().startswith("bearer "):
        return ""
    return header_value[7:].strip()


def create_session(db: Session, user_id: int) -> UserSession:
    token = secrets.token_urlsafe(40)
    session = UserSession(
        user_id=user_id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS),
    )
    db.add(session)
    db.flush()
    return session


def cleanup_expired_sessions(db: Session) -> None:
    now = datetime.utcnow()
    expired_rows = db.scalars(select(UserSession).where(UserSession.expires_at < now).limit(2000)).all()
    for row in expired_rows:
        db.delete(row)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    cleanup_expired_sessions(db)
    session = db.scalar(select(UserSession).where(UserSession.token == token).limit(1))
    if session is None or session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account inactive")

    return user


def resolve_user_from_request(request: Request, db: Session) -> User | None:
    token = _extract_bearer_token(request)
    if not token:
        return None

    cleanup_expired_sessions(db)
    session = db.scalar(select(UserSession).where(UserSession.token == token).limit(1))
    if session is None or session.expires_at < datetime.utcnow():
        return None

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return None

    return user


def require_contributor(user: User = Depends(get_current_user)) -> User:
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


def require_trusted(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin" and user.trust_level not in {"trusted", "verified"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Trusted reviewer role required")
    return user


def choose_initial_trust_level(db: Session) -> str:
    user_count = int(db.scalar(select(func.count(User.id))) or 0)
    return "verified" if user_count == 0 else "new"


def choose_initial_role(db: Session) -> str:
    user_count = int(db.scalar(select(func.count(User.id))) or 0)
    return "admin" if user_count == 0 else "contributor"


def session_token_from_request(request: Request) -> str:
    return _extract_bearer_token(request)
