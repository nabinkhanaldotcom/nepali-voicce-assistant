# backend_api/app/services/audio_service.py

# This file is responsible for:
# 1. receiving and saving uploaded audio
# 2. loading and caching the Faster-Whisper model
# 3. transcribing the saved audio
# 4. passing the transcript to phrase matching

from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile, HTTPException
from faster_whisper import WhisperModel

from app.services.phrase_service import find_best_phrase_match

# Save uploaded files here.
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Allow common audio extensions.
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}

# -----------------------------
# Whisper model configuration
# -----------------------------
#
# This is the ONE active setup for your 2018 Intel Mac.
# Start here.
#
# If this feels too slow, try "small".
# If you later move to stronger hardware, you can test larger models.
# ----------Option 1-----------
# MODEL_SIZE = "small"
# DEVICE = "cpu"
# COMPUTE_TYPE = "int8"
# TRANSCRIPTION_LANGUAGE = "ne"


# ----------Option 2-----------
# for higher computing power
# MODEL_SIZE = "large-v3"
#  if have nvdia graphic card then
# DEVICE = "cuda"
# COMPUTE_TYPE = "float32" -->(Highest precision for CPU, but slower than int8)

# ----------Option 3-----------
MODEL_SIZE = "medium"

# Your current machine is CPU-based.
DEVICE = "cpu"

# Use all 6 CPU threads on your machine.
CPU_THREADS = 6

# int8 is usually the better starting point for CPU.
# It uses less RAM and is faster than fp32 on CPU in Faster-Whisper's published benchmark.
COMPUTE_TYPE = "int8"

# Force Nepali transcription.
# If you want auto-detect again later, change this to:
# TRANSCRIPTION_LANGUAGE = None
TRANSCRIPTION_LANGUAGE = "ne"

# Enable VAD (Voice Activity Detection).
# This removes long silence/no-speech regions before transcription.
USE_VAD_FILTER = True

# Cache the model so it is loaded only once.
_whisper_model = None


def get_whisper_model():
    """
    Load the Faster-Whisper model once and reuse it.

    Why cache it?
    Because model loading is expensive.
    If we load it on every request, the API becomes slow.
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

    Returns metadata about the saved file.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name was provided")

    file_extension = Path(file.filename).suffix.lower()

    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed types: {sorted(ALLOWED_EXTENSIONS)}"
        )

    # Create a unique saved name so files do not overwrite each other.
    unique_name = f"{uuid4()}{file_extension}"
    saved_file_path = UPLOAD_DIR / unique_name

    # Read uploaded bytes and write them to disk.
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
    Transcribe an already-saved audio file.

    Important details:
    - language='ne' tells Whisper to expect Nepali
    - vad_filter=True removes long silent parts
    - condition_on_previous_text=False is often cleaner for short clips
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

    # Collect all segment text into one final transcript.
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
    Save uploaded audio, then transcribe it.
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
    Save uploaded audio, transcribe it, then match transcript against known phrases.
    """
    saved_file_info = await save_uploaded_audio(file)
    transcription_result = transcribe_saved_audio(saved_file_info["saved_path"])
    phrase_match_result = find_best_phrase_match(transcription_result["transcript"])

    return {
        "message": "Audio uploaded, transcribed, and checked for phrase match",
        **transcription_result,
        "phrase_match": phrase_match_result,
        "file_info": saved_file_info
    }