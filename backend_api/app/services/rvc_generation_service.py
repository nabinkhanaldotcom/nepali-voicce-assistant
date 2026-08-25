# backend_api/app/services/rvc_generation_service.py
#
# Phase 3C / security update - RVC voice generation service
#
# Beginner explanation:
# This service connects your normal FastAPI backend to the separate RVC environment.
#
# Your normal backend runs in:
#
#   backend_api/.venv
#
# Your RVC engine runs in:
#
#   backend_api/.venv-rvc
#
# We are keeping them separate because RVC has heavy dependencies like torch,
# fairseq, rmvpe, faiss, etc.
#
# This service does NOT import rvc-python directly.
# Instead, it calls the separate RVC Python executable and asks that Python
# to run:
#
#   backend_api/rvc_engine/run_rvc_inference.py
#
# Security notes:
# - The backend accepts exactly one file from the route.
# - The file extension is allowlisted.
# - The content type is checked when the browser provides it.
# - The file size is capped.
# - ffprobe must prove the file is audio-only.
# - ffprobe must prove the duration is under the limit.
# - The uploaded file is saved with a generated UUID filename.
# - The uploaded original file is never served publicly.
# - The uploaded file is converted to a clean WAV before RVC.
# - ffmpeg and RVC subprocess calls have timeouts.
# - Temporary upload/input files are deleted after processing.
#
# Usage metrics notes:
# - We silently log request metadata.
# - We do NOT store audio contents in the metrics database.
# - We do NOT store transcript text in the metrics database.

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.services.usage_metrics_service import record_usage_event


# backend_api folder
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


# RVC Python executable.
#
# Default Windows path:
#
#   backend_api/.venv-rvc/Scripts/python.exe
#
# On the Azure Linux VM, override this in backend_api/.env:
#
#   RVC_PYTHON_EXE=/home/azureuser/apps/nepali-voicce-assistant/backend_api/.venv-rvc/bin/python
DEFAULT_RVC_PYTHON_EXE = BACKEND_ROOT / ".venv-rvc" / "Scripts" / "python.exe"
RVC_PYTHON_EXE = Path(os.getenv("RVC_PYTHON_EXE", str(DEFAULT_RVC_PYTHON_EXE)))


# RVC wrapper script created in Phase 3B.
RVC_ENGINE_SCRIPT = BACKEND_ROOT / "rvc_engine" / "run_rvc_inference.py"


# Input/output folders.
RVC_UPLOAD_DIR = BACKEND_ROOT / "uploads" / "rvc_generation"
RVC_WAV_INPUT_DIR = BACKEND_ROOT / "data" / "rvc_generated_inputs"
RVC_OUTPUT_DIR = BACKEND_ROOT / "outputs" / "rvc"

RVC_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RVC_WAV_INPUT_DIR.mkdir(parents=True, exist_ok=True)
RVC_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Current safety limits.
#
# Frontend recording limit is 10 seconds.
# Backend allows a small buffer because encoded browser audio may be slightly longer.
MAX_RVC_UPLOAD_BYTES = int(os.getenv("MAX_RVC_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_RVC_DURATION_SECONDS = float(os.getenv("MAX_RVC_DURATION_SECONDS", "12"))

FFPROBE_TIMEOUT_SECONDS = int(os.getenv("FFPROBE_TIMEOUT_SECONDS", "15"))
FFMPEG_TIMEOUT_SECONDS = int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "45"))
RVC_SUBPROCESS_TIMEOUT_SECONDS = int(os.getenv("RVC_SUBPROCESS_TIMEOUT_SECONDS", "180"))


# Audio extensions we accept from Angular or curl.
#
# Note:
# .webm can be audio-only browser recording.
# .mp4 is intentionally not allowed here to avoid accepting normal video files.
# If iOS later records as .mp4, we should add it only after testing audio-only
# ffprobe validation.
SUPPORTED_RVC_INPUT_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".weba",
    ".webm",
    ".ogg",
    ".mpeg",
    ".mpga",
    ".flac",
}


# Browser-provided content type is not trusted by itself,
# but it is still useful as an early reject.
#
# Some browsers may use video/webm for MediaRecorder even when the stream is
# audio-only, so we allow video/webm here but still require ffprobe to prove the
# file has audio streams only.
#
# curl may send application/octet-stream, so we allow it here and rely on
# ffprobe validation.
SUPPORTED_RVC_CONTENT_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/m4a",
    "audio/aac",
    "audio/webm",
    "video/webm",
    "audio/ogg",
    "application/ogg",
    "audio/flac",
    "audio/x-flac",
    "application/octet-stream",
}


SUPPORTED_FFPROBE_FORMATS = {
    "wav",
    "mp3",
    "mov",
    "mp4",
    "m4a",
    "3gp",
    "3g2",
    "mj2",
    "matroska",
    "webm",
    "ogg",
    "flac",
    "mpeg",
}


SUPPORTED_RVC_METHODS = {
    "harvest",
    "crepe",
    "rmvpe",
    "pm",
}


def delete_file_safely(path: Path | str | None) -> None:
    """
    Delete a file without crashing the request if cleanup fails.

    This is used for temporary uploads and generated output files.
    """
    if not path:
        return

    try:
        file_path = Path(path)

        if file_path.exists() and file_path.is_file():
            file_path.unlink()

    except OSError:
        # Do not expose cleanup errors to the user.
        pass


def validate_existing_file(path: Path, label: str) -> None:
    """
    Validate that a required file exists before trying to run RVC.

    This gives a clear FastAPI error instead of a confusing subprocess error.
    """
    if not path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"{label} was not found: {path}",
        )

    if not path.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"{label} is not a file: {path}",
        )


def normalize_rvc_method(method: str | None) -> str:
    """
    Validate pitch extraction method.

    For your model, rmvpe is the best default.
    """
    normalized = (method or "rmvpe").strip().lower()

    if normalized not in SUPPORTED_RVC_METHODS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported RVC method '{method}'. "
                f"Allowed methods: {sorted(SUPPORTED_RVC_METHODS)}"
            ),
        )

    return normalized


def validate_rvc_settings(
    pitch: int,
    index_rate: float,
    protect: float,
) -> None:
    """
    Validate the main RVC settings before passing them to the RVC engine.
    """
    if pitch < -24 or pitch > 24:
        raise HTTPException(
            status_code=400,
            detail="Pitch must be between -24 and 24.",
        )

    if index_rate < 0 or index_rate > 1:
        raise HTTPException(
            status_code=400,
            detail="Index rate must be between 0 and 1.",
        )

    if protect < 0 or protect > 1:
        raise HTTPException(
            status_code=400,
            detail="Protect must be between 0 and 1.",
        )


def normalize_content_type(content_type: str | None) -> str:
    """
    Normalize content type from browser.

    Example:
    audio/webm;codecs=opus -> audio/webm
    """
    if not content_type:
        return ""

    return content_type.split(";")[0].strip().lower()


def validate_upload_metadata(file: UploadFile) -> str:
    """
    Validate filename extension and browser-provided content type.

    This does not prove the file is safe.
    ffprobe validation later is the stronger check.
    """
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No audio file name was provided.",
        )

    file_extension = Path(file.filename).suffix.lower().strip()

    if not file_extension:
        raise HTTPException(
            status_code=400,
            detail="Audio file must have a file extension.",
        )

    if file_extension not in SUPPORTED_RVC_INPUT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported audio file extension '{file_extension}'. "
                f"Allowed extensions: {sorted(SUPPORTED_RVC_INPUT_EXTENSIONS)}"
            ),
        )

    content_type = normalize_content_type(file.content_type)

    if content_type and content_type not in SUPPORTED_RVC_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported uploaded content type '{file.content_type}'. "
                "Please upload an audio file."
            ),
        )

    return file_extension


async def save_rvc_upload(file: UploadFile) -> Path:
    """
    Save uploaded audio to backend_api/uploads/rvc_generation.

    FastAPI UploadFile is similar to MultipartFile in Spring.

    Security:
    - Read only up to MAX_RVC_UPLOAD_BYTES + 1.
    - Reject if too large.
    - Never trust the original filename for storage.
    - Store with UUID filename.
    """
    file_extension = validate_upload_metadata(file)

    file_bytes = await file.read(MAX_RVC_UPLOAD_BYTES + 1)

    if len(file_bytes) > MAX_RVC_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Audio file is too large. Maximum upload size is 25 MB.",
        )

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded audio file is empty.",
        )

    saved_file_name = f"{uuid4()}{file_extension}"
    saved_file_path = RVC_UPLOAD_DIR / saved_file_name

    saved_file_path.write_bytes(file_bytes)

    return saved_file_path


def run_ffprobe(audio_path: Path) -> dict[str, Any]:
    """
    Run ffprobe and return parsed JSON metadata.

    ffprobe is used as the real media validation step.
    A renamed .exe/.js/.html file should fail this check.
    """
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=format_name,duration:stream=index,codec_type,codec_name",
        "-of",
        "json",
        str(audio_path),
    ]

    try:
        completed_process = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT_SECONDS,
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "ffprobe was not found. Install ffmpeg and make sure ffprobe "
                "is available from PowerShell using: ffprobe -version"
            ),
        ) from exc

    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=400,
            detail="Audio validation timed out. Please upload a shorter audio file.",
        ) from exc

    if completed_process.returncode != 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Uploaded file could not be validated as audio. "
                f"ffprobe error: {completed_process.stderr}"
            ),
        )

    try:
        return json.loads(completed_process.stdout)

    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Could not parse audio validation result.",
        ) from exc


def validate_uploaded_audio_file_before_conversion(audio_path: Path) -> None:
    """
    Validate uploaded browser audio before conversion.

    Some mobile browser recordings, especially WebKit/Safari WebM, can be valid
    audio but have no readable container duration before conversion.

    For this first validation step:
    - require at least one stream
    - require audio-only streams
    - require a supported container format
    - do NOT require duration yet

    Duration is checked after ffmpeg converts the upload to a clean WAV.
    """
    probe_result = run_ffprobe(audio_path)

    streams = probe_result.get("streams", [])

    if not streams:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file does not contain an audio stream.",
        )

    stream_types = {
        str(stream.get("codec_type", "")).lower()
        for stream in streams
    }

    if stream_types != {"audio"}:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be audio-only. Video/data/subtitle streams are not allowed.",
        )

    format_info = probe_result.get("format", {})
    format_name = str(format_info.get("format_name", "")).lower()

    format_parts = {
        part.strip()
        for part in format_name.split(",")
        if part.strip()
    }

    if format_parts and not format_parts.intersection(SUPPORTED_FFPROBE_FORMATS):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio container format: {format_name}",
        )


def validate_audio_file_with_ffprobe(audio_path: Path) -> float:
    """
    Validate that the uploaded file is really an audio-only media file.

    This is stronger than trusting:
    - filename
    - extension
    - browser content type

    Rules:
    - Must contain at least one media stream.
    - Every stream must be audio.
    - Duration must be readable.
    - Duration must be under MAX_RVC_DURATION_SECONDS.
    - Container format must be one of the allowed audio-related formats.
    """
    probe_result = run_ffprobe(audio_path)

    streams = probe_result.get("streams", [])

    if not streams:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file does not contain an audio stream.",
        )

    stream_types = {
        str(stream.get("codec_type", "")).lower()
        for stream in streams
    }

    if stream_types != {"audio"}:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be audio-only. Video/data/subtitle streams are not allowed.",
        )

    format_info = probe_result.get("format", {})
    format_name = str(format_info.get("format_name", "")).lower()

    format_parts = {
        part.strip()
        for part in format_name.split(",")
        if part.strip()
    }

    if format_parts and not format_parts.intersection(SUPPORTED_FFPROBE_FORMATS):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio container format: {format_name}",
        )

    duration_text = str(format_info.get("duration", "")).strip()

    try:
        duration_seconds = float(duration_text)

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Could not read audio duration.",
        ) from exc

    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise HTTPException(
            status_code=400,
            detail="Audio duration is invalid.",
        )

    if duration_seconds > MAX_RVC_DURATION_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Audio is too long. Maximum allowed duration is "
                f"{MAX_RVC_DURATION_SECONDS:g} seconds."
            ),
        )

    return duration_seconds


def read_audio_duration_seconds_for_metrics(audio_path: Path | None) -> float | None:
    """
    Best-effort duration reader for analytics.

    This should never break the actual RVC request.
    """
    if audio_path is None:
        return None

    if not audio_path.exists():
        return None

    try:
        probe_result = run_ffprobe(audio_path)
        format_info = probe_result.get("format", {})
        duration_text = str(format_info.get("duration", "")).strip()
        duration_seconds = float(duration_text)

        if math.isfinite(duration_seconds) and duration_seconds > 0:
            return duration_seconds

        return None

    except Exception:
        return None


def convert_audio_to_clean_wav(input_path: Path) -> Path:
    """
    Convert uploaded audio to a clean WAV file before RVC.

    Why:
    Browser recording may be webm/weba/m4a.
    RVC works more predictably when we pass a normal WAV file.

    Security:
    - We map only the first audio stream.
    - We explicitly drop video, subtitle, and data streams.
    - The output is a new clean WAV file created by ffmpeg.
    """
    output_path = RVC_WAV_INPUT_DIR / f"{input_path.stem}_rvc_input.wav"

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-ac",
        "1",
        "-ar",
        "40000",
        "-sample_fmt",
        "s16",
        str(output_path),
    ]

    try:
        completed_process = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "ffmpeg was not found. Install ffmpeg and make sure it is available "
                "from PowerShell using: ffmpeg -version"
            ),
        ) from exc

    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=400,
            detail="Audio conversion timed out. Please upload a shorter audio file.",
        ) from exc

    if completed_process.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to convert uploaded audio to WAV with ffmpeg. "
                f"ffmpeg error: {completed_process.stderr}"
            ),
        )

    if not output_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"ffmpeg finished but did not create WAV file: {output_path}",
        )

    return output_path


def run_rvc_wrapper_script(
    wav_input_path: Path,
    pitch: int,
    index_rate: float,
    protect: float,
    method: str,
) -> Path:
    """
    Call the Phase 3B wrapper script using the RVC Python environment.

    Important:
    FastAPI does not activate .venv-rvc manually.
    Instead, it directly calls the RVC Python executable.

    On Windows:
      backend_api/.venv-rvc/Scripts/python.exe

    On Azure VM:
      backend_api/.venv-rvc/bin/python
    """
    validate_existing_file(RVC_PYTHON_EXE, "RVC Python executable")
    validate_existing_file(RVC_ENGINE_SCRIPT, "RVC wrapper script")

    output_path = RVC_OUTPUT_DIR / f"{wav_input_path.stem}_generated.wav"

    command = [
        str(RVC_PYTHON_EXE),
        str(RVC_ENGINE_SCRIPT),
        "--input",
        str(wav_input_path),
        "--output",
        str(output_path),
        "--pitch",
        str(pitch),
        "--index-rate",
        str(index_rate),
        "--protect",
        str(protect),
        "--method",
        method,
    ]

    try:
        completed_process = subprocess.run(
            command,
            cwd=str(BACKEND_ROOT),
            check=False,
            capture_output=True,
            text=True,
            timeout=RVC_SUBPROCESS_TIMEOUT_SECONDS,
        )

    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "RVC voice generation timed out. "
                "Try a shorter audio file or use a faster server."
            ),
        ) from exc

    if completed_process.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=(
                "RVC voice generation failed. "
                f"STDOUT: {completed_process.stdout} "
                f"STDERR: {completed_process.stderr}"
            ),
        )

    if not output_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"RVC finished but did not create output file: {output_path}",
        )

    return output_path


async def generate_voice_with_rvc(
    file: UploadFile,
    pitch: int = 12,
    index_rate: float = 0.75,
    protect: float = 0.5,
    method: str = "rmvpe",
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Main service function used by the FastAPI route.

    Full flow:
    1. Validate RVC settings
    2. Save uploaded audio with a safe generated filename
    3. Validate uploaded stream/container
    4. Convert to clean WAV
    5. Validate clean WAV duration
    6. Run RVC
    7. Record usage metadata
    8. Delete temporary upload/input files

    Important:
    The generated output file is NOT deleted here.
    The route returns it with FileResponse and deletes it after sending.
    """
    started_at = time.perf_counter()

    uploaded_audio_path: Path | None = None
    wav_input_path: Path | None = None
    duration_seconds: float | None = None
    uploaded_file_size_bytes: int | None = None
    generated_audio_path: Path | None = None
    output_bytes: int | None = None
    normalized_method = method or "rmvpe"

    try:
        normalized_method = normalize_rvc_method(method)

        validate_rvc_settings(
            pitch=pitch,
            index_rate=index_rate,
            protect=protect,
        )

        uploaded_audio_path = await save_rvc_upload(file)

        if uploaded_audio_path.exists():
            uploaded_file_size_bytes = uploaded_audio_path.stat().st_size

        validate_uploaded_audio_file_before_conversion(uploaded_audio_path)

        wav_input_path = convert_audio_to_clean_wav(uploaded_audio_path)

        duration_seconds = validate_audio_file_with_ffprobe(wav_input_path)

        generated_audio_path = run_rvc_wrapper_script(
            wav_input_path=wav_input_path,
            pitch=pitch,
            index_rate=index_rate,
            protect=protect,
            method=normalized_method,
        )

        if generated_audio_path.exists():
            output_bytes = generated_audio_path.stat().st_size

        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/generate-voice",
            action="rvc_generate",
            success=True,
            status_code=200,
            request_context=request_context,
            original_filename=file.filename,
            content_type=file.content_type,
            upload_bytes=uploaded_file_size_bytes,
            duration_seconds=duration_seconds,
            rvc_pitch=pitch,
            rvc_index_rate=index_rate,
            rvc_protect=protect,
            rvc_method=normalized_method,
            output_bytes=output_bytes,
            processing_ms=processing_ms,
        )

        return {
            "generatedAudioPath": generated_audio_path,
            "durationSeconds": duration_seconds,
            "uploadBytes": uploaded_file_size_bytes,
            "outputBytes": output_bytes,
            "method": normalized_method,
        }

    except HTTPException as exc:
        if duration_seconds is None:
            duration_seconds = read_audio_duration_seconds_for_metrics(wav_input_path)

        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/generate-voice",
            action="rvc_generate",
            success=False,
            status_code=exc.status_code,
            error_message=str(exc.detail),
            request_context=request_context,
            original_filename=file.filename,
            content_type=file.content_type,
            upload_bytes=uploaded_file_size_bytes,
            duration_seconds=duration_seconds,
            rvc_pitch=pitch,
            rvc_index_rate=index_rate,
            rvc_protect=protect,
            rvc_method=normalized_method,
            output_bytes=output_bytes,
            processing_ms=processing_ms,
        )

        raise

    except Exception as exc:
        if duration_seconds is None:
            duration_seconds = read_audio_duration_seconds_for_metrics(wav_input_path)

        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/generate-voice",
            action="rvc_generate",
            success=False,
            status_code=500,
            error_message=str(exc),
            request_context=request_context,
            original_filename=file.filename,
            content_type=file.content_type,
            upload_bytes=uploaded_file_size_bytes,
            duration_seconds=duration_seconds,
            rvc_pitch=pitch,
            rvc_index_rate=index_rate,
            rvc_protect=protect,
            rvc_method=normalized_method,
            output_bytes=output_bytes,
            processing_ms=processing_ms,
        )

        raise

    finally:
        delete_file_safely(uploaded_audio_path)
        delete_file_safely(wav_input_path)