# app/api/v1/stt_tts.py

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse

from app.services.stt_service import transcribe_nepali
from app.services.tts_service import synthesize_dummy_wav

router = APIRouter()


@router.post("/stt")
async def stt(audio: UploadFile = File(...)):
    """
    Speech-to-Text endpoint.
    Angular will POST the audio blob here as form-data field "audio".
    """
    try:
        text = await transcribe_nepali(audio)
        return {"text": text}
    except Exception as e:
        # Minimal logging; you can upgrade later
        print("[STT] Error:", e)
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to transcribe audio."},
        )


@router.post("/tts")
async def tts(payload: dict):
    """
    Text-to-Speech endpoint (currently dummy).
    Angular sends JSON: { "text": "..." }.
    """
    text = payload.get("text", "")
    return synthesize_dummy_wav(text)
