# backend_api/app/services/audio_service.py

# This file is responsible for:
# 1. saving uploaded audio
# 2. loading the Faster-Whisper model
# 3. transcribing audio
# 4. doing normal phrase matching
# 5. doing debug phrase matching
# 6. providing a default phrase threshold

from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile, HTTPException
from faster_whisper import WhisperModel

from app.services.phrase_service import (
    find_best_phrase_match,
    get_phrase_debug_scores
)

# Folder where uploaded audio files are stored
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Allowed audio file extensions
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}

# -----------------------------
# Whisper configuration
# -----------------------------

MODEL_SIZE = "medium"
DEVICE = "cpu"
CPU_THREADS = 6
COMPUTE_TYPE = "int8"

# Force Nepali transcription
TRANSCRIPTION_LANGUAGE = "ne"

# Use Voice Activity Detection to trim silence/no-speech parts
USE_VAD_FILTER = True

# Default threshold for phrases that do not define their own minimum_score
DEFAULT_MATCH_MINIMUM_SCORE = 70.0

# Cache the model so it loads only once
_whisper_model = None


def get_whisper_model():
    """
    Load the Whisper model once and reuse it.
    """
    global _whisper_model

    if _whisper_model is None:
        _whisper_model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
            cpu_threads=CPU_THREADS
        )

    return _whisper_model


async def save_uploaded_audio(file: UploadFile):
    """
    Validate and save an uploaded audio file.
    """
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
    """
    Transcribe a saved audio file using Faster-Whisper.
    """
    model = get_whisper_model()

    transcribe_options = {
        "beam_size": 5,
        "condition_on_previous_text": False
    }

    if TRANSCRIPTION_LANGUAGE is not None:
        transcribe_options["language"] = TRANSCRIPTION_LANGUAGE

    if USE_VAD_FILTER:
        transcribe_options["vad_filter"] = True

    segments, info = model.transcribe(saved_path, **transcribe_options)

    transcript_parts = []

    for segment in segments:
        cleaned_text = segment.text.strip()
        if cleaned_text:
            transcript_parts.append(cleaned_text)

    full_transcript = " ".join(transcript_parts).strip()

    return {
        "transcript": full_transcript,
        "detected_language": info.language,
        "language_probability": info.language_probability,
        "language_mode": TRANSCRIPTION_LANGUAGE if TRANSCRIPTION_LANGUAGE else "auto"
    }


async def transcribe_uploaded_audio(file: UploadFile):
    """
    Save uploaded audio and transcribe it.
    """
    saved_file_info = await save_uploaded_audio(file)
    transcription_result = transcribe_saved_audio(saved_file_info["saved_path"])

    return {
        "message": "Audio uploaded and transcribed successfully",
        **transcription_result,
        "file_info": saved_file_info
    }


async def transcribe_and_match_audio(file: UploadFile):
    """
    Save uploaded audio, transcribe it, and return the best phrase match.
    """
    saved_file_info = await save_uploaded_audio(file)
    transcription_result = transcribe_saved_audio(saved_file_info["saved_path"])

    phrase_match_result = find_best_phrase_match(
        transcription_result["transcript"],
        default_minimum_score=DEFAULT_MATCH_MINIMUM_SCORE
    )

    return {
        "message": "Audio uploaded, transcribed, and checked for phrase match",
        **transcription_result,
        "default_match_threshold": DEFAULT_MATCH_MINIMUM_SCORE,
        "phrase_match": phrase_match_result,
        "file_info": saved_file_info
    }


async def transcribe_and_debug_match_audio(file: UploadFile):
    """
    Save uploaded audio, transcribe it, and return debug scoring details
    for all phrases.
    """
    saved_file_info = await save_uploaded_audio(file)
    transcription_result = transcribe_saved_audio(saved_file_info["saved_path"])

    phrase_match_result = find_best_phrase_match(
        transcription_result["transcript"],
        default_minimum_score=DEFAULT_MATCH_MINIMUM_SCORE
    )

    debug_scores = get_phrase_debug_scores(
        transcription_result["transcript"],
        default_minimum_score=DEFAULT_MATCH_MINIMUM_SCORE
    )

    return {
        "message": "Audio uploaded, transcribed, and debug phrase scores generated",
        **transcription_result,
        "default_match_threshold": DEFAULT_MATCH_MINIMUM_SCORE,
        "phrase_match": phrase_match_result,
        "debug_scores": debug_scores,
        "file_info": saved_file_info
    }