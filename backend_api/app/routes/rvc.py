# backend_api/app/routes/rvc.py
#
# RVC voice generation route.
#
# Login can be turned off with AUTH_REQUIRED=false.
# Usage metrics are recorded silently on the backend.

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.services.auth_service import AuthenticatedUser, require_authenticated_user
from app.services.rvc_generation_service import (
    delete_file_safely,
    generate_voice_with_rvc,
)
from app.services.usage_metrics_service import (
    build_request_usage_context,
    record_usage_event,
)

router = APIRouter()


@router.post("/generate-voice")
async def generate_voice(
    request: Request,
    files: list[UploadFile] = File(..., alias="file"),
    pitch: int = Form(6),
    indexRate: float = Form(0.75),
    protect: float = Form(0.5),
    method: str = Form("rmvpe"),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    request_context = build_request_usage_context(
        request=request,
        username=current_user.username,
    )

    if len(files) != 1:
        record_usage_event(
            endpoint="/generate-voice",
            action="rvc_generate",
            success=False,
            status_code=400,
            error_message="Exactly one audio file must be uploaded.",
            request_context=request_context,
            rvc_pitch=pitch,
            rvc_index_rate=indexRate,
            rvc_protect=protect,
            rvc_method=method,
        )

        raise HTTPException(
            status_code=400,
            detail="Exactly one audio file must be uploaded.",
        )

    generated_result: Any = await generate_voice_with_rvc(
        file=files[0],
        pitch=pitch,
        index_rate=indexRate,
        protect=protect,
        method=method,
        request_context=request_context,
    )

    if isinstance(generated_result, dict):
        generated_audio_path = Path(generated_result["generatedAudioPath"])
    else:
        generated_audio_path = Path(generated_result)

    return FileResponse(
        path=str(generated_audio_path),
        media_type="audio/wav",
        filename=generated_audio_path.name,
        background=BackgroundTask(delete_file_safely, generated_audio_path),
    )