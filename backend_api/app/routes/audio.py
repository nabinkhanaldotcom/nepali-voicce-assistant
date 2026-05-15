from fastapi import APIRouter, UploadFile, File
from app.services.audio_service import (
    save_uploaded_audio,
    transcribe_uploaded_audio,
    transcribe_and_match_audio
)

router = APIRouter()


@router.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    result = await save_uploaded_audio(file)

    return {
        "message": "Audio uploaded successfully",
        **result
    }


@router.post("/transcribe-audio")
async def transcribe_audio(file: UploadFile = File(...)):
    result = await transcribe_uploaded_audio(file)
    return result


@router.post("/transcribe-and-match")
async def transcribe_and_match(file: UploadFile = File(...)):
    result = await transcribe_and_match_audio(file)
    return result