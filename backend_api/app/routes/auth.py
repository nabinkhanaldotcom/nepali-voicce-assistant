# backend_api/app/routes/auth.py
#
# Login routes.
#
# Even when the frontend login screen is hidden, keeping these endpoints is useful
# because you can turn AUTH_REQUIRED=true later without rebuilding the whole app.

from fastapi import APIRouter, Depends

from app.services.auth_service import (
    AuthenticatedUser,
    LoginRequest,
    LoginResponse,
    authenticate_login,
    get_guest_username,
    is_auth_required,
    require_authenticated_user,
)

router = APIRouter()


@router.get("/auth/config")
async def auth_config():
    """
    Frontend can call this later if you want a dynamic login toggle.

    Current frontend below does not need this, because we are fully hiding login.
    """
    return {
        "authRequired": is_auth_required(),
        "guestUsername": get_guest_username(),
    }


@router.post("/auth/login", response_model=LoginResponse)
async def login(login_request: LoginRequest):
    return authenticate_login(
        username=login_request.username,
        password=login_request.password,
    )


@router.get("/auth/me")
async def get_current_user(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    return {
        "username": current_user.username,
        "authenticated": current_user.authenticated,
        "authMode": current_user.auth_mode,
    }