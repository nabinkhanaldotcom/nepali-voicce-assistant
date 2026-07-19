# backend_api/app/routes/rvc.py
#
# Phase 3C / security update - RVC voice generation route
#
# Beginner explanation:
# This route is like a Spring Controller endpoint.
#
# Angular calls:
#
#   POST /generate-voice
#
# with one audio file.
#
# This route:
# - requires login
# - requires exactly one uploaded file
# - rejects multiple uploaded files
# - receives RVC settings like pitch/indexRate/protect/method
# - calls rvc_generation_service
# - returns generated WAV audio to the browser
# - deletes the generated server-side output file after sending it

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.services.auth_service import require_authenticated_user
from app.services.rvc_generation_service import (
    delete_file_safely,
    generate_voice_with_rvc,
)


router = APIRouter(
    dependencies=[Depends(require_authenticated_user)]
)


@router.post("/generate-voice")
async def generate_voice(
    files: list[UploadFile] = File(..., alias="file"),
    pitch: int = Form(6),
    indexRate: float = Form(0.75),
    protect: float = Form(0.5),
    method: str = Form("rmvpe"),
):
    """
    Generate Artist's Voice using the local RVC model.

    Form fields:
    - file: exactly one uploaded audio file
    - pitch: semitone shift. Try 0, 4, 6, 8, 10.
    - indexRate: search feature ratio. Good default: 0.75.
    - protect: protect voiceless consonants/breath sounds. Good default: 0.5.
    - method: pitch extraction method. Good default: rmvpe.

    Returns:
    - generated WAV audio file
    """
    if len(files) != 1:
        raise HTTPException(
            status_code=400,
            detail="Exactly one audio file must be uploaded.",
        )

    generated_audio_path = await generate_voice_with_rvc(
        file=files[0],
        pitch=pitch,
        index_rate=indexRate,
        protect=protect,
        method=method,
    )

    return FileResponse(
        path=str(generated_audio_path),
        media_type="audio/wav",
        filename=generated_audio_path.name,
        background=BackgroundTask(delete_file_safely, generated_audio_path),
    )