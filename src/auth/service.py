"""Registration, login, session resolution and logout (database-backed). Errors are generic by design."""
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from src.auth import security as sec
from src.db.errors import guarded
from src.db.models import AuthSession, User, utcnow
from src.db.session import session_scope

logger = logging.getLogger("auth")


class AuthError(Exception):
    """status is machine-readable and safe to return; message is generic."""

    def __init__(self, status: str, message: str, http: int = 401, problems=None):
        super().__init__(message)
        self.status, self.message, self.http, self.problems = status, message, http, problems or []


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    display_name: Optional[str]
    session_id: str


def _ttl() -> timedelta:
    return timedelta(minutes=sec.env_int("ACCESS_TOKEN_TTL_MIN", 60))


def _absolute() -> timedelta:
    return timedelta(hours=sec.env_int("SESSION_ABSOLUTE_HOURS", 12))


def _max_failures() -> int:
    return sec.env_int("LOGIN_MAX_FAILURES", 8)


def _lock_minutes() -> int:
    return sec.env_int("LOGIN_LOCK_MINUTES", 15)


def registration_open() -> bool:
    return os.environ.get("ALLOW_REGISTRATION", "1").lower() not in ("0", "false", "no")


@guarded
def register(email: str, password: str, display_name: Optional[str] = None) -> dict:
    if not registration_open():
        raise AuthError("registration_closed", "Registration is not available.", 403)
    email = sec.normalize_email(email)
    problems = sec.validate_email(email) + sec.validate_password(password or "", email)
    if problems:
        raise AuthError("invalid_input", "Registration details are not acceptable.", 422, problems)
    name = (display_name or "").strip()[:80] or None
    pw_hash = sec.hash_password(password)
    with session_scope() as s:
        if s.scalar(select(User.id).where(User.email == email)):
            raise AuthError("registration_failed", "Registration could not be completed.", 409)
        u = User(id=sec.new_id(), email=email, password_hash=pw_hash, display_name=name, failed_attempts=0, is_active=True)
        s.add(u)
        try:
            s.flush()                       # a concurrent duplicate hits the UNIQUE constraint here
        except Exception:
            s.rollback()
            raise AuthError("registration_failed", "Registration could not be completed.", 409) from None
        out = {"id": u.id, "email": u.email, "display_name": u.display_name}
    logger.info("user registered id=%s", out["id"])
    return out


@guarded
def login(email: str, password: str) -> dict:
    email = sec.normalize_email(email)
    generic = AuthError("invalid_credentials", "Invalid credentials or too many attempts. Try again later.", 401)
    with session_scope() as s:
        u = s.scalar(select(User).where(User.email == email))
        now = utcnow()
        if u is None or not u.is_active:
            sec.verify_password(sec.DUMMY_HASH, password or "")     # same work whether or not the account exists
            raise generic
        if u.locked_until and u.locked_until > now:
            sec.verify_password(sec.DUMMY_HASH, password or "")
            raise generic
        if not sec.verify_password(u.password_hash, password or ""):
            u.failed_attempts = (u.failed_attempts or 0) + 1
            if u.failed_attempts >= _max_failures():
                u.locked_until = now + timedelta(minutes=_lock_minutes())
                u.failed_attempts = 0
            s.commit()                      # keep the counter even though we raise
            raise generic
        if sec.needs_rehash(u.password_hash):
            u.password_hash = sec.hash_password(password)
        u.failed_attempts, u.locked_until, u.last_login_at = 0, None, now
        token = sec.new_token()
        sess = AuthSession(id=sec.new_id(), user_id=u.id, token_hash=sec.token_digest(token), created_at=now,
                           expires_at=now + _ttl(), absolute_expires_at=now + _absolute())
        s.add(sess)
        out = {"access_token": token, "token_type": "bearer", "expires_at": sess.expires_at.isoformat() + "Z",
               "user": {"id": u.id, "email": u.email, "display_name": u.display_name}}
    logger.info("login ok user=%s", out["user"]["id"])
    return out


@guarded
def resolve(token: str) -> AuthUser:
    """Validate a bearer token; slides the idle expiry (bounded by the absolute cap). Raises AuthError otherwise."""
    if not token or len(token) > 200:
        raise AuthError("unauthenticated", "Authentication required.")
    digest = sec.token_digest(token)
    with session_scope() as s:
        sess = s.scalar(select(AuthSession).where(AuthSession.token_hash == digest))
        if sess is None:
            raise AuthError("unauthenticated", "Authentication required.")
        now = utcnow()
        if sess.revoked_at is not None or now >= sess.expires_at or now >= sess.absolute_expires_at:
            raise AuthError("session_expired", "Your session has expired. Please sign in again.")
        u = s.get(User, sess.user_id)
        if u is None or not u.is_active:
            raise AuthError("unauthenticated", "Authentication required.")
        target = min(now + _ttl(), sess.absolute_expires_at)
        if (target - sess.expires_at) > timedelta(seconds=60):       # limit write amplification
            sess.expires_at = target
        return AuthUser(id=u.id, email=u.email, display_name=u.display_name, session_id=sess.id)


@guarded
def logout(session_id: str) -> None:
    with session_scope() as s:
        sess = s.get(AuthSession, session_id)
        if sess is not None and sess.revoked_at is None:
            sess.revoked_at = utcnow()


@guarded
def purge_sessions() -> int:
    from sqlalchemy import delete
    with session_scope() as s:
        r = s.execute(delete(AuthSession).where((AuthSession.absolute_expires_at < utcnow()) | (AuthSession.revoked_at.is_not(None))))
        return r.rowcount or 0
