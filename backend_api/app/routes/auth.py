# backend_api/app/routes/auth.py
#
# Login routes.
#
# Beginner explanation:
# This file is like an AuthController in Spring.
#
# Angular will call:
#
#   POST /auth/login
#
# If username/password are valid, FastAPI returns a token.
# Angular then sends that token with future backend requests.

from fastapi import APIRouter, Depends

from app.services.auth_service import (
    AuthenticatedUser,
    LoginRequest,
    LoginResponse,
    authenticate_login,
    require_authenticated_user,
)


router = APIRouter()


@router.post("/auth/login", response_model=LoginResponse)
async def login(login_request: LoginRequest):
    """
    Login with username/password.

    Request JSON:
    {
      "username": "demo",
      "password": "your-password"
    }

    Response:
    {
      "access_token": "...",
      "token_type": "bearer",
      "expires_in_seconds": 28800,
      "username": "demo"
    }
    """
    return authenticate_login(
        username=login_request.username,
        password=login_request.password,
    )


@router.get("/auth/me")
async def get_current_user(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """
    Verify that the current login token is still valid.
    """
    return {
        "username": current_user.username,
        "authenticated": True,
    }