# backend_api/app/routes/audio.py

# This file defines the audio-related API endpoints.

from fastapi import APIRouter, UploadFile, File, Form

from app.services.audio_service import (
    save_uploaded_audio,
    transcribe_uploaded_audio,
    transcribe_and_match_audio,
    transcribe_and_debug_match_audio
)

router = APIRouter()


@router.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    """
    Save an uploaded audio file and return file metadata.
    """
    result = await save_uploaded_audio(file)

    return {
        "message": "Audio uploaded successfully",
        **result
    }


@router.post("/transcribe-audio")
async def transcribe_audio(
    file: UploadFile = File(...),
    provider: str = Form("auto")
):
    """
    Save uploaded audio and return transcription only.

    provider:
    - auto
    - local
    - openai
    """
    result = await transcribe_uploaded_audio(file, provider=provider)
    return result


@router.post("/transcribe-and-match")
async def transcribe_and_match(
    file: UploadFile = File(...),
    provider: str = Form("auto")
):
    """
    Save uploaded audio, transcribe it, and return the best phrase match.

    provider:
    - auto
    - local
    - openai
    """
    result = await transcribe_and_match_audio(file, provider=provider)
    return result


@router.post("/transcribe-and-debug-match")
async def transcribe_and_debug_match(
    file: UploadFile = File(...),
    provider: str = Form("auto")
):
    """
    Save uploaded audio, transcribe it, and return debug scoring
    for all phrases.

    provider:
    - auto
    - local
    - openai
    """
    result = await transcribe_and_debug_match_audio(file, provider=provider)
    return result