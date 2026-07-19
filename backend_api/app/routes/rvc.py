# backend_api/app/routes/rvc.py
#
# Phase 3C - RVC voice generation route
#
# Beginner explanation:
# This route is like a Spring Controller endpoint.
#
# Angular will eventually call:
#
#   POST /generate-voice
#
# with an audio file.
#
# This route will:
# - receive the file
# - receive RVC settings like pitch/indexRate/protect/method
# - call rvc_generation_service
# - return generated WAV audio to the browser

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.services.rvc_generation_service import generate_voice_with_rvc


router = APIRouter()


@router.post("/generate-voice")
async def generate_voice(
    file: UploadFile = File(...),
    pitch: int = Form(6),
    indexRate: float = Form(0.75),
    protect: float = Form(0.5),
    method: str = Form("rmvpe"),
):
    """
    Generate uncle-style voice using the local RVC model.

    Form fields:
    - file: uploaded audio file
    - pitch: semitone shift. Try 0, 4, 6, 8, 10.
    - indexRate: search feature ratio. Good default: 0.75.
    - protect: protect voiceless consonants/breath sounds. Good default: 0.5.
    - method: pitch extraction method. Good default: rmvpe.

    Returns:
    - generated WAV audio file
    """
    generated_audio_path = await generate_voice_with_rvc(
        file=file,
        pitch=pitch,
        index_rate=indexRate,
        protect=protect,
        method=method,
    )

    return FileResponse(
        path=str(generated_audio_path),
        media_type="audio/wav",
        filename=generated_audio_path.name,
    )