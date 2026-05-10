from fastapi import APIRouter, UploadFile, File
from app.services.audio_service import save_uploaded_audio, fake_transcribe_audio

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
    result = await fake_transcribe_audio(file)
    return result