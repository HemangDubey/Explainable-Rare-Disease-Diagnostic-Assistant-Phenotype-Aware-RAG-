"""Authentication endpoints and the request gate. Tokens travel in the Authorization header (no cookies, so no CSRF surface)."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.auth import service
from src.auth.service import AuthError, AuthUser

router = APIRouter(prefix="/api/auth", tags=["auth"])
PUBLIC_PATHS = {"/", "/api/auth/login", "/api/auth/register", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


def _http(e: AuthError) -> HTTPException:
    detail = {"status": e.status, "message": e.message}
    if e.problems:
        detail["problems"] = e.problems
    headers = {"WWW-Authenticate": "Bearer"} if e.http == 401 else None
    return HTTPException(status_code=e.http, detail=detail, headers=headers)


def bearer_token(request: Request) -> Optional[str]:
    h = request.headers.get("authorization", "")
    parts = h.split(None, 1)
    return parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else None


def auth_gate(request: Request) -> None:
    """Global dependency: every route except PUBLIC_PATHS needs a valid, unexpired, unrevoked session."""
    if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
        return
    try:
        request.state.user = service.resolve(bearer_token(request))
    except AuthError as e:
        raise _http(e)


def current_user(request: Request) -> AuthUser:
    """Per-route dependency that exposes the identity the gate established (ownership checks use user.id)."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail={"status": "unauthenticated", "message": "Authentication required."}, headers={"WWW-Authenticate": "Bearer"})
    return user


class Credentials(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=256)


class Registration(Credentials):
    display_name: Optional[str] = Field(default=None, max_length=80)


@router.post("/register", status_code=201)
def register(body: Registration):
    try:
        return service.register(body.email, body.password, body.display_name)
    except AuthError as e:
        raise _http(e)


@router.post("/login")
def login(body: Credentials):
    try:
        return service.login(body.email, body.password)
    except AuthError as e:
        raise _http(e)


@router.post("/logout")
def logout(request: Request):
    user = current_user(request)
    service.logout(user.session_id)
    return {"status": "logged_out"}


@router.get("/me")
def me(request: Request):
    u = current_user(request)
    return {"id": u.id, "email": u.email, "display_name": u.display_name}
