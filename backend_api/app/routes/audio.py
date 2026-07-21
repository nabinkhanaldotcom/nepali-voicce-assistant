# backend_api/app/routes/audio.py
#
# Audio endpoints.
#
# Login can be turned off with AUTH_REQUIRED=false.
# Usage metrics are recorded silently on the backend.

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.services.auth_service import AuthenticatedUser, require_authenticated_user
from app.services.audio_service import (
    convert_audio_for_download,
    get_audio_duration_seconds,
    save_uploaded_audio,
    transcribe_and_match_audio,
    transcribe_uploaded_audio,
)
from app.services.usage_metrics_service import (
    build_request_usage_context,
    record_usage_event,
)

router = APIRouter()


def get_http_exception_message(exc: HTTPException) -> str:
    if exc.detail is None:
        return ""

    return str(exc.detail)


def get_file_info(result: dict[str, Any]) -> dict[str, Any]:
    file_info = result.get("fileInfo")

    if isinstance(file_info, dict):
        return file_info

    return {}


@router.post("/upload-audio")
async def upload_audio(
    request: Request,
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    started_at = time.perf_counter()

    request_context = build_request_usage_context(
        request=request,
        username=current_user.username,
    )

    try:
        result = await save_uploaded_audio(file)

        duration_seconds = None
        saved_path = result.get("savedPath")

        if saved_path:
            duration_seconds = get_audio_duration_seconds(str(saved_path))

        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/upload-audio",
            action="upload_audio",
            success=True,
            status_code=200,
            request_context=request_context,
            original_filename=result.get("originalFilename"),
            content_type=result.get("contentType"),
            upload_bytes=result.get("sizeInBytes"),
            duration_seconds=duration_seconds,
            processing_ms=processing_ms,
        )

        return {
            "message": "Audio uploaded successfully",
            **result,
        }

    except HTTPException as exc:
        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/upload-audio",
            action="upload_audio",
            success=False,
            status_code=exc.status_code,
            error_message=get_http_exception_message(exc),
            request_context=request_context,
            original_filename=file.filename,
            content_type=file.content_type,
            processing_ms=processing_ms,
        )

        raise

    except Exception as exc:
        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/upload-audio",
            action="upload_audio",
            success=False,
            status_code=500,
            error_message=str(exc),
            request_context=request_context,
            original_filename=file.filename,
            content_type=file.content_type,
            processing_ms=processing_ms,
        )

        raise


@router.post("/transcribe-audio")
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    provider: str = Form("local_whisper"),
    openaiModel: str = Form("gpt-4o-mini-transcribe"),
    tonePreset: str = Form("original"),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    started_at = time.perf_counter()

    request_context = build_request_usage_context(
        request=request,
        username=current_user.username,
    )

    try:
        result = await transcribe_uploaded_audio(
            file=file,
            provider=provider,
            openai_model=openaiModel,
            tone_preset=tonePreset,
        )

        file_info = get_file_info(result)
        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/transcribe-audio",
            action="transcribe_audio",
            success=True,
            status_code=200,
            request_context=request_context,
            original_filename=file_info.get("originalFilename"),
            content_type=file_info.get("contentType"),
            upload_bytes=file_info.get("sizeInBytes"),
            duration_seconds=result.get("durationSeconds"),
            provider=result.get("providerUsed"),
            model=result.get("modelUsed"),
            tone_preset=result.get("tonePreset"),
            processing_ms=processing_ms,
        )

        return result

    except HTTPException as exc:
        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/transcribe-audio",
            action="transcribe_audio",
            success=False,
            status_code=exc.status_code,
            error_message=get_http_exception_message(exc),
            request_context=request_context,
            original_filename=file.filename,
            content_type=file.content_type,
            provider=provider,
            model=openaiModel,
            tone_preset=tonePreset,
            processing_ms=processing_ms,
        )

        raise

    except Exception as exc:
        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/transcribe-audio",
            action="transcribe_audio",
            success=False,
            status_code=500,
            error_message=str(exc),
            request_context=request_context,
            original_filename=file.filename,
            content_type=file.content_type,
            provider=provider,
            model=openaiModel,
            tone_preset=tonePreset,
            processing_ms=processing_ms,
        )

        raise


@router.post("/transcribe-and-match")
async def transcribe_and_match(
    request: Request,
    file: UploadFile = File(...),
    provider: str = Form("local_whisper"),
    openaiModel: str = Form("gpt-4o-mini-transcribe"),
    tonePreset: str = Form("original"),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    started_at = time.perf_counter()

    request_context = build_request_usage_context(
        request=request,
        username=current_user.username,
    )

    try:
        result = await transcribe_and_match_audio(
            file=file,
            provider=provider,
            openai_model=openaiModel,
            tone_preset=tonePreset,
        )

        file_info = get_file_info(result)
        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/transcribe-and-match",
            action="transcribe_and_match",
            success=True,
            status_code=200,
            request_context=request_context,
            original_filename=file_info.get("originalFilename"),
            content_type=file_info.get("contentType"),
            upload_bytes=file_info.get("sizeInBytes"),
            duration_seconds=result.get("durationSeconds"),
            provider=result.get("providerUsed"),
            model=result.get("modelUsed"),
            tone_preset=result.get("tonePreset"),
            processing_ms=processing_ms,
        )

        return result

    except HTTPException as exc:
        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/transcribe-and-match",
            action="transcribe_and_match",
            success=False,
            status_code=exc.status_code,
            error_message=get_http_exception_message(exc),
            request_context=request_context,
            original_filename=file.filename,
            content_type=file.content_type,
            provider=provider,
            model=openaiModel,
            tone_preset=tonePreset,
            processing_ms=processing_ms,
        )

        raise

    except Exception as exc:
        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/transcribe-and-match",
            action="transcribe_and_match",
            success=False,
            status_code=500,
            error_message=str(exc),
            request_context=request_context,
            original_filename=file.filename,
            content_type=file.content_type,
            provider=provider,
            model=openaiModel,
            tone_preset=tonePreset,
            processing_ms=processing_ms,
        )

        raise


@router.post("/convert-audio-download")
async def convert_audio_download(
    request: Request,
    file: UploadFile = File(...),
    outputFormat: str = Form("wav"),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    started_at = time.perf_counter()

    request_context = build_request_usage_context(
        request=request,
        username=current_user.username,
    )

    try:
        result = await convert_audio_for_download(
            file=file,
            output_format=outputFormat,
        )

        converted_path = Path(result["convertedPath"])
        output_bytes = None

        if converted_path.exists():
            output_bytes = converted_path.stat().st_size

        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/convert-audio-download",
            action="convert_audio_download",
            success=True,
            status_code=200,
            request_context=request_context,
            original_filename=file.filename,
            content_type=file.content_type,
            output_bytes=output_bytes,
            processing_ms=processing_ms,
        )

        return FileResponse(
            path=result["convertedPath"],
            media_type=result["mediaType"],
            filename=result["downloadFilename"],
        )

    except HTTPException as exc:
        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/convert-audio-download",
            action="convert_audio_download",
            success=False,
            status_code=exc.status_code,
            error_message=get_http_exception_message(exc),
            request_context=request_context,
            original_filename=file.filename,
            content_type=file.content_type,
            processing_ms=processing_ms,
        )

        raise

    except Exception as exc:
        processing_ms = int((time.perf_counter() - started_at) * 1000)

        record_usage_event(
            endpoint="/convert-audio-download",
            action="convert_audio_download",
            success=False,
            status_code=500,
            error_message=str(exc),
            request_context=request_context,
            original_filename=file.filename,
            content_type=file.content_type,
            processing_ms=processing_ms,
        )

        raise