# backend_api/app/routes/audio.py
#
# This file defines audio-related API endpoints.
#
# Beginner explanation:
# A route file is like a Spring Controller.
# It should stay thin:
# - receive HTTP request
# - read form fields
# - call service methods
# - return the service result
#
# Real logic should stay inside app/services/*.py.

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.services.audio_service import (
    convert_audio_for_download,
    save_uploaded_audio,
    transcribe_and_match_audio,
    transcribe_uploaded_audio,
)

router = APIRouter()


@router.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    """
    Save an uploaded audio file and return file metadata.

    This endpoint does NOT transcribe.
    It is useful for testing file upload by itself.
    """

    result = await save_uploaded_audio(file)

    return {
        "message": "Audio uploaded successfully",
        **result,
    }


@router.post("/transcribe-audio")
async def transcribe_audio(
    file: UploadFile = File(...),
    provider: str = Form("local_whisper"),
    openaiModel: str = Form("gpt-4o-mini-transcribe"),
    tonePreset: str = Form("original"),
):
    """
    Save uploaded audio and return transcription result.

    Provider is manual only:
    - local_whisper
    - openai_whisper

    No auto provider.
    No score-based fallback.
    """

    result = await transcribe_uploaded_audio(
        file=file,
        provider=provider,
        openai_model=openaiModel,
        tone_preset=tonePreset,
    )

    return result


@router.post("/transcribe-and-match")
async def transcribe_and_match(
    file: UploadFile = File(...),
    provider: str = Form("local_whisper"),
    openaiModel: str = Form("gpt-4o-mini-transcribe"),
    tonePreset: str = Form("original"),
):
    """
    Save uploaded audio, transcribe it, and check phrase aliases.

    This is the main endpoint Angular should call.

    Provider is manual only:
    - local_whisper
    - openai_whisper

    OpenAI model is only used when provider=openai_whisper:
    - gpt-4o-mini-transcribe
    - gpt-4o-transcribe
    """

    result = await transcribe_and_match_audio(
        file=file,
        provider=provider,
        openai_model=openaiModel,
        tone_preset=tonePreset,
    )

    return result


@router.post("/convert-audio-download")
async def convert_audio_download(
    file: UploadFile = File(...),
    outputFormat: str = Form("wav"),
):
    """
    Convert uploaded audio into a selected download format.

    Beginner explanation:
    Angular sends the current audio file/blob plus the selected format:
    - wav
    - mp3
    - m4a

    The backend uses ffmpeg to do real audio conversion.
    This is different from only renaming a file extension.
    """

    result = await convert_audio_for_download(
        file=file,
        output_format=outputFormat,
    )

    return FileResponse(
        path=result["convertedPath"],
        media_type=result["mediaType"],
        filename=result["downloadFilename"],
    )