# backend_api/app/services/auth_service.py
#
# Simple private-demo authentication service.
#
# Update:
# AUTH_REQUIRED=false turns off backend login enforcement.
#
# Beginner explanation:
# - When AUTH_REQUIRED=true, protected routes require a JWT token.
# - When AUTH_REQUIRED=false, protected routes allow a guest/demo user.
#
# This lets you hide the login screen on the frontend while still keeping the
# option to turn login back on later.

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

load_dotenv()

JWT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 8 * 60

bearer_scheme = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in_seconds: int
    username: str


class AuthenticatedUser(BaseModel):
    username: str
    authenticated: bool = True
    auth_mode: str = "jwt"


def is_auth_required() -> bool:
    """
    Read whether login is required.

    In .env:

    AUTH_REQUIRED=true
    or
    AUTH_REQUIRED=false
    """
    value = os.getenv("AUTH_REQUIRED", "true").strip().lower()
    return value not in {"false", "0", "no", "off"}


def get_guest_username() -> str:
    return os.getenv("GUEST_USERNAME", "guest").strip() or "guest"


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server authentication is not configured. Missing {name}.",
        )

    return value


def get_access_token_expire_minutes() -> int:
    value = os.getenv(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        str(DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    try:
        return int(value)
    except ValueError:
        return DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES


def create_access_token(username: str) -> tuple[str, int]:
    jwt_secret_key = get_required_env("JWT_SECRET_KEY")
    expire_minutes = get_access_token_expire_minutes()

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    payload = {
        "sub": username,
        "type": "access",
        "exp": expires_at,
    }

    token = jwt.encode(
        payload,
        jwt_secret_key,
        algorithm=JWT_ALGORITHM,
    )

    expires_in_seconds = expire_minutes * 60

    return token, expires_in_seconds


def authenticate_login(username: str, password: str) -> LoginResponse:
    """
    Check username/password from environment variables.

    If AUTH_REQUIRED=false, this still returns a lightweight guest response.
    The frontend will not show the login screen anyway.
    """
    if not is_auth_required():
        return LoginResponse(
            access_token="",
            token_type="none",
            expires_in_seconds=0,
            username=get_guest_username(),
        )

    expected_username = os.getenv("APP_LOGIN_USERNAME", "demo")
    expected_password = get_required_env("APP_LOGIN_PASSWORD")

    username_matches = secrets.compare_digest(
        username.strip(),
        expected_username,
    )

    password_matches = secrets.compare_digest(
        password,
        expected_password,
    )

    if not username_matches or not password_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password bro.",
        )

    access_token, expires_in_seconds = create_access_token(expected_username)

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in_seconds=expires_in_seconds,
        username=expected_username,
    )


async def require_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """
    Dependency used by protected FastAPI routes.

    If AUTH_REQUIRED=false:
    - no token is required
    - route gets a guest user

    If AUTH_REQUIRED=true:
    - Authorization: Bearer <token> is required
    """
    if not is_auth_required():
        return AuthenticatedUser(
            username=get_guest_username(),
            authenticated=False,
            auth_mode="guest",
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme.",
        )

    token = credentials.credentials
    jwt_secret_key = get_required_env("JWT_SECRET_KEY")

    try:
        payload = jwt.decode(
            token,
            jwt_secret_key,
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login expired bro. Please log in again.",
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login token.",
        ) from exc

    username = payload.get("sub")
    token_type = payload.get("type")

    if not username or token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login token.",
        )

    return AuthenticatedUser(
        username=str(username),
        authenticated=True,
        auth_mode="jwt",
    )