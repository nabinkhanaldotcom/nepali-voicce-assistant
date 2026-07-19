# backend_api/app/services/auth_service.py
#
# Simple private-demo authentication service.
#
# Beginner explanation:
# This file handles:
# - checking username/password
# - creating a login token
# - reading a login token from future requests
# - blocking protected endpoints when the token is missing/invalid
#
# This is similar to Spring Security checking a JWT before allowing
# access to a controller method.
#
# Important:
# This is good for a private demo.
# For a real production app with many users, use database-backed users,
# password hashing, account lockout/rate limiting, and/or a real auth provider.

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


def get_required_env(name: str) -> str:
    """
    Read a required environment variable.

    We do not hardcode real passwords or token secrets in source code.
    """
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
    """
    Create a signed JWT access token.

    JWT means:
    - the backend signs the token
    - the browser sends it back later
    - the backend can verify that it created the token
    """
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

    Environment variables:
    - APP_LOGIN_USERNAME
    - APP_LOGIN_PASSWORD
    - JWT_SECRET_KEY
    """
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

    If a request does not include:

      Authorization: Bearer <token>

    or if the token is invalid/expired, the request is rejected.
    """
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

    return AuthenticatedUser(username=str(username))