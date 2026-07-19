# backend_api/app/services/rvc_generation_service.py
#
# Phase 3C - RVC voice generation service
#
# Beginner explanation:
# This service connects your normal FastAPI backend to the separate RVC environment.
#
# Your normal backend runs in:
#
#   backend_api/venv
#
# Your RVC engine runs in:
#
#   backend_api/.venv-rvc
#
# We are keeping them separate because RVC has heavy dependencies like torch,
# fairseq, rmvpe, faiss, etc. Keeping it separate protects your already-working
# FastAPI / Whisper backend.
#
# This service does NOT import rvc-python directly.
# Instead, it calls:
#
#   backend_api/.venv-rvc/Scripts/python.exe
#
# and asks that Python to run:
#
#   backend_api/rvc_engine/run_rvc_inference.py
#
# This is similar to a Java app calling another command-line tool with ProcessBuilder.

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile


# backend_api folder
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

# RVC Python executable.
#
# Default Windows path:
# backend_api/.venv-rvc/Scripts/python.exe
#
# You can override this later using an environment variable:
# RVC_PYTHON_EXE=C:\some\other\python.exe
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

# Audio types we will accept from Angular.
SUPPORTED_RVC_INPUT_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".weba",
    ".webm",
    ".ogg",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".flac",
}

SUPPORTED_RVC_METHODS = {
    "harvest",
    "crepe",
    "rmvpe",
    "pm",
}


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


async def save_rvc_upload(file: UploadFile) -> Path:
    """
    Save uploaded audio to backend_api/uploads/rvc_generation.

    FastAPI UploadFile is similar to MultipartFile in Spring.
    """
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No audio file name was provided.",
        )

    file_extension = Path(file.filename).suffix.lower()

    if not file_extension:
        file_extension = ".webm"

    if file_extension not in SUPPORTED_RVC_INPUT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported audio type '{file_extension}'. "
                f"Allowed types: {sorted(SUPPORTED_RVC_INPUT_EXTENSIONS)}"
            ),
        )

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded audio file is empty.",
        )

    saved_file_name = f"{uuid4()}{file_extension}"
    saved_file_path = RVC_UPLOAD_DIR / saved_file_name

    saved_file_path.write_bytes(file_bytes)

    return saved_file_path


def convert_audio_to_clean_wav(input_path: Path) -> Path:
    """
    Convert uploaded audio to a clean WAV file before RVC.

    Why:
    Browser recording may be webm/weba.
    RVC works more predictably when we pass a normal WAV file.

    We use ffmpeg because it handles many audio formats.
    """
    output_path = RVC_WAV_INPUT_DIR / f"{input_path.stem}_rvc_input.wav"

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
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
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "ffmpeg was not found. Install ffmpeg and make sure it is available "
                "from PowerShell using: ffmpeg -version"
            ),
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
    Instead, it directly calls:

      backend_api/.venv-rvc/Scripts/python.exe

    That Python already knows about rvc-python.
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

    completed_process = subprocess.run(
        command,
        cwd=str(BACKEND_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )

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
    pitch: int = 6,
    index_rate: float = 0.75,
    protect: float = 0.5,
    method: str = "rmvpe",
) -> Path:
    """
    Main service function used by the FastAPI route.

    Full flow:
    1. Save uploaded audio
    2. Convert it to clean WAV
    3. Run RVC wrapper script
    4. Return path to generated WAV
    """
    normalized_method = normalize_rvc_method(method)

    validate_rvc_settings(
        pitch=pitch,
        index_rate=index_rate,
        protect=protect,
    )

    uploaded_audio_path = await save_rvc_upload(file)
    wav_input_path = convert_audio_to_clean_wav(uploaded_audio_path)

    generated_audio_path = run_rvc_wrapper_script(
        wav_input_path=wav_input_path,
        pitch=pitch,
        index_rate=index_rate,
        protect=protect,
        method=normalized_method,
    )

    return generated_audio_path