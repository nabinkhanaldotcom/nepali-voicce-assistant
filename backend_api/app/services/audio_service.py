from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile, HTTPException
from faster_whisper import WhisperModel

from app.services.phrase_service import find_best_phrase_match

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}

MODEL_SIZE = "small"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

# Set this to "ne" when you want to force Nepali transcription.
# Set it to None when you want automatic language detection.
# TRANSCRIPTION_LANGUAGE = "ne"
TRANSCRIPTION_LANGUAGE = "None"

_whisper_model = None


def get_whisper_model():
    global _whisper_model

    if _whisper_model is None:
        _whisper_model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE
        )

    return _whisper_model


async def save_uploaded_audio(file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name was provided")

    file_extension = Path(file.filename).suffix.lower()

    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed types: {sorted(ALLOWED_EXTENSIONS)}"
        )

    unique_name = f"{uuid4()}{file_extension}"
    saved_file_path = UPLOAD_DIR / unique_name

    file_bytes = await file.read()
    saved_file_path.write_bytes(file_bytes)

    return {
        "original_filename": file.filename,
        "saved_filename": unique_name,
        "content_type": file.content_type,
        "size_in_bytes": len(file_bytes),
        "saved_path": str(saved_file_path)
    }


def transcribe_saved_audio(saved_path: str):
    model = get_whisper_model()
    segments, info = model.transcribe(
        saved_path,
        beam_size=5
    )

    transcript_parts = []

    for segment in segments:
        cleaned_text = segment.text.strip()
        if cleaned_text:
            transcript_parts.append(cleaned_text)

    full_transcript = " ".join(transcript_parts).strip()

    return {
        "transcript": full_transcript,
        "detected_language": info.language,
        "language_probability": info.language_probability
    }


async def transcribe_uploaded_audio(file: UploadFile):
    saved_file_info = await save_uploaded_audio(file)
    transcription_result = transcribe_saved_audio(saved_file_info["saved_path"])

    return {
        "message": "Audio uploaded and transcribed successfully",
        **transcription_result,
        "file_info": saved_file_info
    }


async def transcribe_and_match_audio(file: UploadFile):
    saved_file_info = await save_uploaded_audio(file)
    transcription_result = transcribe_saved_audio(saved_file_info["saved_path"])
    phrase_match_result = find_best_phrase_match(transcription_result["transcript"])

    return {
        "message": "Audio uploaded, transcribed, and checked for phrase match",
        **transcription_result,
        "phrase_match": phrase_match_result,
        "file_info": saved_file_info
    }