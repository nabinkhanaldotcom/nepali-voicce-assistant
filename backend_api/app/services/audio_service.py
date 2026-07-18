# backend_api/app/services/audio_service.py
#
# This file is responsible for the real audio workflow.
#
# What this file does:
# 1. Validate and save uploaded audio
# 2. Transcribe using manually selected provider:
#    - local_whisper
#    - openai_whisper
# 3. Estimate OpenAI transcription cost
# 4. Call phrase_service to find a saved matching phrase clip
# 5. Convert audio into download formats:
#    - wav
#    - mp3
#    - m4a
# 6. Return a clean response for Angular
#
# What this file intentionally does NOT do anymore:
# - no auto provider
# - no local-to-OpenAI fallback
# - no score-based fallback
# - no debug scoring
# - no minimum score threshold
# - no used minimum score

import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import av
from dotenv import load_dotenv
from fastapi import HTTPException, UploadFile
from faster_whisper import WhisperModel
from openai import OpenAI

from app.services.phrase_service import (
    find_phrase_match,
    get_devanagari_alias_hints,
)

# Load backend_api/.env if it exists.
#
# This is optional. You can also use terminal export:
# export OPENAI_API_KEY="your_key_here"
load_dotenv()

# backend_api folder
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

# Folder where uploaded/temp audio files are stored:
# backend_api/uploads
UPLOAD_DIR = BACKEND_ROOT / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Folder where converted download files are stored:
# backend_api/uploads/downloads
DOWNLOAD_DIR = UPLOAD_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Allowed audio file extensions.
ALLOWED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".webm",
    ".weba",
    ".ogg",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".flac",
}

# Download formats the UI is allowed to request.
SUPPORTED_DOWNLOAD_FORMATS = {
    "wav",
    "mp3",
    "m4a",
}

DOWNLOAD_MEDIA_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
}

# -----------------------------
# Local Faster-Whisper configuration
# -----------------------------
#
# You can override these from terminal or backend_api/.env later.
#
# Example:
# LOCAL_WHISPER_MODEL_SIZE=medium
# LOCAL_WHISPER_DEVICE=cpu
# LOCAL_WHISPER_COMPUTE_TYPE=int8
# LOCAL_WHISPER_CPU_THREADS=6
LOCAL_WHISPER_MODEL_SIZE = os.getenv("LOCAL_WHISPER_MODEL_SIZE", "medium")
LOCAL_WHISPER_DEVICE = os.getenv("LOCAL_WHISPER_DEVICE", "cpu")
LOCAL_WHISPER_COMPUTE_TYPE = os.getenv("LOCAL_WHISPER_COMPUTE_TYPE", "int8")
LOCAL_WHISPER_CPU_THREADS = int(os.getenv("LOCAL_WHISPER_CPU_THREADS", "6"))

# Nepali language code.
TRANSCRIPTION_LANGUAGE = os.getenv("TRANSCRIPTION_LANGUAGE", "ne")

# VAD = Voice Activity Detection.
# This helps remove silence.
USE_VAD_FILTER = os.getenv("USE_VAD_FILTER", "true").lower() == "true"

# -----------------------------
# Manual provider configuration
# -----------------------------
SUPPORTED_TRANSCRIPTION_PROVIDERS = {
    "local_whisper",
    "openai_whisper",
}

# Backward-compatible aliases while you are refactoring old UI/code.
PROVIDER_ALIASES = {
    "local": "local_whisper",
    "openai": "openai_whisper",
}

SUPPORTED_OPENAI_TRANSCRIBE_MODELS = {
    "gpt-4o-mini-transcribe",
    "gpt-4o-transcribe",
}

DEFAULT_OPENAI_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"

# Your requested simple estimate constants.
#
# Important:
# This is only an app-side estimate for your UI.
# Actual billing truth is always your OpenAI usage/billing dashboard.
OPENAI_TRANSCRIBE_COSTS_PER_MINUTE = {
    "gpt-4o-mini-transcribe": 0.003,
    "gpt-4o-transcribe": 0.006,
}

SUPPORTED_TONE_PRESETS = {
    "original",
    "happy",
    "sad",
    "punchline",
}

DEFAULT_TONE_PRESET = "original"

# Cache the local Whisper model so it loads only once.
_whisper_model: WhisperModel | None = None

# Cache the OpenAI client so it initializes only once.
_openai_client: OpenAI | None = None


def round_optional(value: Any, digits: int = 3) -> float | None:
    """
    Round a numeric value if it exists.
    """

    if value is None:
        return None

    return round(float(value), digits)


def normalize_transcription_provider(provider: str) -> str:
    """
    Validate and normalize the provider string.

    Allowed final values:
    - local_whisper
    - openai_whisper

    Old aliases supported:
    - local -> local_whisper
    - openai -> openai_whisper
    """

    normalized = (provider or "local_whisper").strip().lower()
    normalized = PROVIDER_ALIASES.get(normalized, normalized)

    if normalized not in SUPPORTED_TRANSCRIPTION_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported provider '{provider}'. "
                f"Allowed providers: {sorted(SUPPORTED_TRANSCRIPTION_PROVIDERS)}"
            ),
        )

    return normalized


def normalize_openai_model(openai_model: str | None) -> str:
    """
    Validate OpenAI transcription model name.
    """

    model = (openai_model or DEFAULT_OPENAI_TRANSCRIBE_MODEL).strip()

    if model not in SUPPORTED_OPENAI_TRANSCRIBE_MODELS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported OpenAI transcription model '{openai_model}'. "
                f"Allowed models: {sorted(SUPPORTED_OPENAI_TRANSCRIBE_MODELS)}"
            ),
        )

    return model


def normalize_tone_preset(tone_preset: str | None) -> str:
    """
    Validate tone preset.

    Tone is currently only returned back in the response.
    Future voice generation will use it.
    """

    normalized = (tone_preset or DEFAULT_TONE_PRESET).strip().lower()

    if normalized not in SUPPORTED_TONE_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported tone preset '{tone_preset}'. "
                f"Allowed tone presets: {sorted(SUPPORTED_TONE_PRESETS)}"
            ),
        )

    return normalized


def normalize_download_format(output_format: str | None) -> str:
    """
    Validate the requested audio download format.

    Beginner explanation:
    The browser sends text like "mp3".
    We only allow known safe values so the user cannot create arbitrary files.
    """

    normalized = (output_format or "wav").strip().lower()

    if normalized not in SUPPORTED_DOWNLOAD_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported download format '{output_format}'. "
                f"Allowed formats: {sorted(SUPPORTED_DOWNLOAD_FORMATS)}"
            ),
        )

    return normalized


def build_download_filename(original_filename: str | None, output_format: str) -> str:
    """
    Build the file name the browser will download.

    Example:
    original recording.webm + mp3 -> recording.mp3
    """

    if original_filename:
        base_name = Path(original_filename).stem.strip()
    else:
        base_name = ""

    if not base_name:
        base_name = "converted_audio"

    return f"{base_name}.{output_format}"


def get_audio_duration_seconds(saved_path: str) -> float | None:
    """
    Estimate audio duration using PyAV.

    We use this for OpenAI cost estimation.
    """

    container = None

    try:
        container = av.open(saved_path)

        if container.duration is not None:
            return float(container.duration * av.time_base)

        audio_stream = next(
            (stream for stream in container.streams if stream.type == "audio"),
            None,
        )

        if (
            audio_stream
            and audio_stream.duration is not None
            and audio_stream.time_base is not None
        ):
            return float(audio_stream.duration * audio_stream.time_base)

        return None

    except Exception:
        return None

    finally:
        if container is not None:
            container.close()


def estimate_openai_transcription_cost_usd(
    audio_duration_seconds: float | None,
    model_name: str,
) -> float:
    """
    Estimate transcription cost using your configured per-minute values.

    This is only an estimate.
    """

    if audio_duration_seconds is None:
        return 0.0

    per_minute_cost = OPENAI_TRANSCRIBE_COSTS_PER_MINUTE.get(model_name)

    if per_minute_cost is None:
        return 0.0

    return round((audio_duration_seconds / 60.0) * per_minute_cost, 6)


def get_whisper_model() -> WhisperModel:
    """
    Load the local Faster-Whisper model once and reuse it.

    Beginner explanation:
    Loading the model is expensive.
    We do not want to reload it for every request.
    So we keep it in a module-level variable called _whisper_model.
    """

    global _whisper_model

    if _whisper_model is None:
        _whisper_model = WhisperModel(
            LOCAL_WHISPER_MODEL_SIZE,
            device=LOCAL_WHISPER_DEVICE,
            compute_type=LOCAL_WHISPER_COMPUTE_TYPE,
            cpu_threads=LOCAL_WHISPER_CPU_THREADS,
        )

    return _whisper_model


def get_openai_client() -> OpenAI:
    """
    Load the OpenAI client once and reuse it.

    SECURITY:
    OPENAI_API_KEY must come from backend environment variable.
    Never put your API key in Angular/browser code.
    Never commit your API key to GitHub.
    """

    global _openai_client

    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise HTTPException(
                status_code=500,
                detail=(
                    "OPENAI_API_KEY is not set on the backend server. "
                    "Set it in your terminal or backend_api/.env."
                ),
            )

        _openai_client = OpenAI(api_key=api_key)

    return _openai_client


async def save_uploaded_audio(file: UploadFile) -> dict[str, Any]:
    """
    Validate and save an uploaded audio file.

    FastAPI UploadFile is similar to MultipartFile in Spring.
    """

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name was provided.")

    file_extension = Path(file.filename).suffix.lower()

    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{file_extension}'. "
                f"Allowed types: {sorted(ALLOWED_EXTENSIONS)}"
            ),
        )

    unique_name = f"{uuid4()}{file_extension}"
    saved_file_path = UPLOAD_DIR / unique_name

    file_bytes = await file.read()
    saved_file_path.write_bytes(file_bytes)

    return {
        "originalFilename": file.filename,
        "savedFilename": unique_name,
        "contentType": file.content_type,
        "sizeInBytes": len(file_bytes),
        "savedPath": str(saved_file_path),
    }


async def convert_audio_for_download(
    file: UploadFile,
    output_format: str = "wav",
) -> dict[str, Any]:
    """
    Convert an uploaded audio file into wav, mp3, or m4a.

    Beginner explanation:
    The browser may record audio as webm.
    If the user wants mp3, wav, or m4a, we must really convert the audio.
    Renaming recording.webm to recording.mp3 is not enough.

    This function uses ffmpeg.
    """

    normalized_format = normalize_download_format(output_format)

    saved_file_info = await save_uploaded_audio(file)
    input_path = Path(saved_file_info["savedPath"])

    download_filename = build_download_filename(
        original_filename=saved_file_info.get("originalFilename"),
        output_format=normalized_format,
    )

    converted_file_path = DOWNLOAD_DIR / f"{uuid4()}_{download_filename}"

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
    ]

    if normalized_format == "wav":
        command.extend(
            [
                "-acodec",
                "pcm_s16le",
                "-ar",
                "44100",
                "-ac",
                "1",
            ]
        )

    elif normalized_format == "mp3":
        command.extend(
            [
                "-acodec",
                "libmp3lame",
                "-b:a",
                "192k",
            ]
        )

    elif normalized_format == "m4a":
        command.extend(
            [
                "-acodec",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
            ]
        )

    command.append(str(converted_file_path))

    try:
        completed_process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "ffmpeg was not found. Install ffmpeg and make sure it is available "
                "from your terminal PATH."
            ),
        ) from exc

    if completed_process.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=(
                "Audio conversion failed. "
                f"ffmpeg error: {completed_process.stderr.strip()}"
            ),
        )

    return {
        "convertedPath": str(converted_file_path),
        "downloadFilename": download_filename,
        "mediaType": DOWNLOAD_MEDIA_TYPES[normalized_format],
    }


def build_openai_transcription_prompt() -> str:
    """
    Build a small Nepali prompt for OpenAI transcription.

    This gives OpenAI a few known phrase hints from your phrase library.
    """

    phrase_hints = get_devanagari_alias_hints(max_aliases=12)

    prompt_parts = [
        "यो अडियो नेपाली भाषामा छ। कृपया सम्भव भएसम्म सही नेपाली लिपिमा ट्रान्सक्रिप्शन देऊ।"
    ]

    if phrase_hints:
        prompt_parts.append(
            "यी शब्द वा वाक्यांशहरू उपयोगी हुन सक्छन्: "
            + ", ".join(phrase_hints)
        )

    return " ".join(prompt_parts)


def transcribe_saved_audio_local(saved_path: str) -> dict[str, Any]:
    """
    Transcribe a saved audio file with local Faster-Whisper.
    """

    model = get_whisper_model()

    transcribe_options: dict[str, Any] = {
        "beam_size": 5,
        "condition_on_previous_text": False,
    }

    if TRANSCRIPTION_LANGUAGE:
        transcribe_options["language"] = TRANSCRIPTION_LANGUAGE

    if USE_VAD_FILTER:
        transcribe_options["vad_filter"] = True

    segments, info = model.transcribe(saved_path, **transcribe_options)

    transcript_parts: list[str] = []

    for segment in segments:
        cleaned_text = segment.text.strip()

        if cleaned_text:
            transcript_parts.append(cleaned_text)

    full_transcript = " ".join(transcript_parts).strip()

    return {
        "providerUsed": "local_whisper",
        "modelUsed": LOCAL_WHISPER_MODEL_SIZE,
        "transcript": full_transcript,
        "detectedLanguage": info.language,
        "languageProbability": round_optional(info.language_probability, 3),
    }


def extract_openai_transcription_text(transcription_response: Any) -> str:
    """
    Safely extract text from the OpenAI SDK response.
    """

    if hasattr(transcription_response, "text") and transcription_response.text is not None:
        return str(transcription_response.text).strip()

    if isinstance(transcription_response, dict):
        return str(transcription_response.get("text", "")).strip()

    return str(transcription_response).strip()


def transcribe_saved_audio_openai(
    saved_path: str,
    openai_model: str,
) -> dict[str, Any]:
    """
    Transcribe a saved audio file with OpenAI.

    The API key stays on the backend.
    Angular never sees the key.
    """

    client = get_openai_client()
    prompt_text = build_openai_transcription_prompt()

    with open(saved_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model=openai_model,
            file=audio_file,
            response_format="json",
            language=TRANSCRIPTION_LANGUAGE,
            prompt=prompt_text,
        )

    transcript_text = extract_openai_transcription_text(transcription)

    return {
        "providerUsed": "openai_whisper",
        "modelUsed": openai_model,
        "transcript": transcript_text,
        "detectedLanguage": TRANSCRIPTION_LANGUAGE,
        "languageProbability": None,
    }


def transcribe_saved_audio(
    saved_path: str,
    provider: str,
    openai_model: str,
) -> dict[str, Any]:
    """
    Run exactly one transcription provider.

    No auto mode.
    No fallback.
    """

    if provider == "local_whisper":
        return transcribe_saved_audio_local(saved_path)

    if provider == "openai_whisper":
        return transcribe_saved_audio_openai(
            saved_path=saved_path,
            openai_model=openai_model,
        )

    raise HTTPException(status_code=400, detail=f"Unsupported provider '{provider}'.")


def build_output_decision(tone_preset: str) -> dict[str, Any]:
    """
    Placeholder for future voice generation.

    For now, phrase clips can be replayed, but true generated voice output
    is not implemented yet.
    """

    return {
        "status": "placeholder",
        "message": "Voice generation is not implemented yet.",
        "tonePreset": tone_preset,
        "shouldGenerateVoice": False,
    }


def build_pipeline_response(
    message: str,
    saved_file_info: dict[str, Any],
    provider_requested: str,
    tone_preset: str,
    transcription_result: dict[str, Any],
    duration_seconds: float | None,
    estimated_cost_usd: float,
    phrase_match_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the clean response shape expected by Angular.
    """

    return {
        "message": message,
        "providerRequested": provider_requested,
        "providerUsed": transcription_result["providerUsed"],
        "modelUsed": transcription_result["modelUsed"],
        "transcript": transcription_result["transcript"],
        "detectedLanguage": transcription_result["detectedLanguage"],
        "languageProbability": transcription_result["languageProbability"],
        "durationSeconds": round_optional(duration_seconds, 3),
        "estimatedCostUsd": round_optional(estimated_cost_usd, 6) or 0.0,
        "tonePreset": tone_preset,
        "score": phrase_match_result["score"],
        "matchedClip": phrase_match_result["matchedClip"],
        "outputDecision": build_output_decision(tone_preset),
        "fileInfo": saved_file_info,
    }


async def run_audio_pipeline(
    file: UploadFile,
    provider: str,
    openai_model: str,
    tone_preset: str,
    message: str,
) -> dict[str, Any]:
    """
    Common pipeline used by:
    - /transcribe-audio
    - /transcribe-and-match
    """

    provider_requested = normalize_transcription_provider(provider)
    selected_openai_model = normalize_openai_model(openai_model)
    selected_tone_preset = normalize_tone_preset(tone_preset)

    saved_file_info = await save_uploaded_audio(file)
    saved_path = saved_file_info["savedPath"]

    duration_seconds = get_audio_duration_seconds(saved_path)

    transcription_result = transcribe_saved_audio(
        saved_path=saved_path,
        provider=provider_requested,
        openai_model=selected_openai_model,
    )

    estimated_cost_usd = 0.0

    if provider_requested == "openai_whisper":
        estimated_cost_usd = estimate_openai_transcription_cost_usd(
            audio_duration_seconds=duration_seconds,
            model_name=selected_openai_model,
        )

    phrase_match_result = find_phrase_match(transcription_result["transcript"])

    return build_pipeline_response(
        message=message,
        saved_file_info=saved_file_info,
        provider_requested=provider_requested,
        tone_preset=selected_tone_preset,
        transcription_result=transcription_result,
        duration_seconds=duration_seconds,
        estimated_cost_usd=estimated_cost_usd,
        phrase_match_result=phrase_match_result,
    )


async def transcribe_uploaded_audio(
    file: UploadFile,
    provider: str = "local_whisper",
    openai_model: str = DEFAULT_OPENAI_TRANSCRIBE_MODEL,
    tone_preset: str = DEFAULT_TONE_PRESET,
) -> dict[str, Any]:
    """
    Save uploaded audio and transcribe it.

    This still returns score/matchedClip for convenience,
    but Angular should mainly use /transcribe-and-match.
    """

    return await run_audio_pipeline(
        file=file,
        provider=provider,
        openai_model=openai_model,
        tone_preset=tone_preset,
        message="Audio uploaded and transcribed successfully",
    )


async def transcribe_and_match_audio(
    file: UploadFile,
    provider: str = "local_whisper",
    openai_model: str = DEFAULT_OPENAI_TRANSCRIBE_MODEL,
    tone_preset: str = DEFAULT_TONE_PRESET,
) -> dict[str, Any]:
    """
    Save uploaded audio, transcribe it, and return phrase match result.
    """

    return await run_audio_pipeline(
        file=file,
        provider=provider,
        openai_model=openai_model,
        tone_preset=tone_preset,
        message="Audio uploaded, transcribed, and checked for phrase match",
    )