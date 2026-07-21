# backend_api/app/routes/usage.py
#
# Protected admin-only usage metrics endpoints.
#
# Important:
# Login can be turned off for demo users, but usage metrics should NOT become
# public. So these endpoints use a separate admin token:
#
# X-Usage-Admin-Token: <USAGE_ADMIN_TOKEN from .env>

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.services.usage_metrics_service import (
    get_recent_usage_events,
    get_usage_summary,
)

router = APIRouter(
    prefix="/usage",
    tags=["usage"],
)


def require_usage_admin_token(
    x_usage_admin_token: str | None = Header(default=None),
) -> None:
    expected_token = os.getenv("USAGE_ADMIN_TOKEN", "").strip()

    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="USAGE_ADMIN_TOKEN is not configured on the server.",
        )

    if not x_usage_admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usage admin token is required.",
        )

    if not secrets.compare_digest(x_usage_admin_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid usage admin token.",
        )


@router.get("/summary", dependencies=[Depends(require_usage_admin_token)])
async def usage_summary(
    days: int = Query(30, ge=1, le=365),
):
    return get_usage_summary(days=days)


@router.get("/recent", dependencies=[Depends(require_usage_admin_token)])
async def usage_recent(
    limit: int = Query(50, ge=1, le=500),
):
    return get_recent_usage_events(limit=limit)