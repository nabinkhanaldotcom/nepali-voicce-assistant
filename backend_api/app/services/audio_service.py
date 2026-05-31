# backend_api/app/services/audio_service.py

# This file is responsible for:
# 1. saving uploaded audio
# 2. loading the local Faster-Whisper model
# 3. calling OpenAI transcription when needed
# 4. choosing between local / OpenAI / auto provider modes
# 5. applying fallback rules
# 6. estimating transcription cost
# 7. returning final phrase-matching results

import os
from pathlib import Path
from uuid import uuid4

import av
from fastapi import UploadFile, HTTPException
from faster_whisper import WhisperModel
from openai import OpenAI

from app.services.phrase_service import (
    find_best_phrase_match,
    get_phrase_debug_scores,
    get_devanagari_alias_hints
)

# Folder where uploaded audio files are stored
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Allowed audio file extensions
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}

# -----------------------------
# Local Faster-Whisper configuration
# -----------------------------
# MODEL_SIZE = "small"
MODEL_SIZE = "medium"
# MODEL_SIZE = "large"
DEVICE = "cpu"
# DEVICE = "gpu"
CPU_THREADS = 6
COMPUTE_TYPE = "int8"
TRANSCRIPTION_LANGUAGE = "ne"
# VAD = Voice Activity Detection
USE_VAD_FILTER = True

# -----------------------------
# Hybrid provider configuration
# -----------------------------
SUPPORTED_TRANSCRIPTION_PROVIDERS = {"auto", "local", "openai"}

# Default threshold for phrases that do not define their own minimum_score
DEFAULT_MATCH_MINIMUM_SCORE = 70.0

# In "auto" mode, fallback to OpenAI if the local score is too close to the threshold.
AUTO_FALLBACK_SCORE_MARGIN = 8.0

# If both local and OpenAI return matched phrases, OpenAI must be this much better
# before we switch away from local.
OPENAI_PROVIDER_SWITCH_SCORE_MARGIN = 3.0

# OpenAI transcription model.
# We use the cheaper model by default.
OPENAI_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"

# Cost estimates per minute based on current official pricing.
# These are estimates for your internal tracking, not billing truth.
OPENAI_TRANSCRIBE_COSTS_PER_MINUTE = {
    "gpt-4o-mini-transcribe": 0.003,
    "gpt-4o-transcribe": 0.006
}

# Cache the local Whisper model so it loads only once
_whisper_model = None

# Cache the OpenAI client so it also initializes only once
_openai_client = None


def round_optional(value, digits=3):
    """
    Round a numeric value if it exists, otherwise return None.
    """
    if value is None:
        return None

    return round(float(value), digits)


def normalize_transcription_provider(provider: str) -> str:
    """
    Validate and normalize the provider string.

    Allowed:
    - auto
    - local
    - openai
    """
    normalized = (provider or "auto").strip().lower()

    if normalized not in SUPPORTED_TRANSCRIPTION_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider '{provider}'. Allowed providers: {sorted(SUPPORTED_TRANSCRIPTION_PROVIDERS)}"
        )

    return normalized


def get_audio_duration_seconds(saved_path: str):
    """
    Estimate the audio duration using PyAV.

    We use this for simple cost tracking.
    """
    container = None

    try:
        container = av.open(saved_path)

        # Most files will have a container-level duration
        if container.duration is not None:
            return float(container.duration / av.time_base)

        # Fallback: try the first audio stream duration
        audio_stream = next((stream for stream in container.streams if stream.type == "audio"), None)

        if audio_stream and audio_stream.duration is not None and audio_stream.time_base is not None:
            return float(audio_stream.duration * audio_stream.time_base)

        return None
    except Exception:
        return None
    finally:
        if container is not None:
            container.close()


def estimate_openai_transcription_cost_usd(audio_duration_seconds, model_name: str):
    """
    Estimate transcription cost using the configured per-minute pricing.

    This is only an internal estimate for debugging / tracking.
    """
    if audio_duration_seconds is None:
        return None

    per_minute_cost = OPENAI_TRANSCRIBE_COSTS_PER_MINUTE.get(model_name)

    if per_minute_cost is None:
        return None

    return round((audio_duration_seconds / 60.0) * per_minute_cost, 6)


def get_whisper_model():
    """
    Load the local Faster-Whisper model once and reuse it.
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


def get_openai_client():
    """
    Load the OpenAI client once and reuse it.

    IMPORTANT:
    The API key must come from an environment variable on the backend.
    Never put the key in Angular/browser code.
    """
    global _openai_client

    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set on the backend server.")

        _openai_client = OpenAI(api_key=api_key)

    return _openai_client


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


def build_openai_transcription_prompt():
    """
    Build a small Nepali prompt for OpenAI transcription.

    Why this exists:
    OpenAI's docs say prompts can improve specific words and writing style.
    We give the model a few known Devanagari phrase hints from our phrase library.
    """
    phrase_hints = get_devanagari_alias_hints(max_aliases=12)

    prompt_parts = [
        "यो अडियो नेपाली भाषामा छ। कृपया सम्भव भएसम्म सही नेपाली लिपिमा ट्रान्सक्रिप्शन देऊ।"
    ]

    if phrase_hints:
        prompt_parts.append("यी शब्द वा वाक्यांशहरू उपयोगी हुन सक्छन्: " + ", ".join(phrase_hints))

    return " ".join(prompt_parts)


def transcribe_saved_audio_local(saved_path: str):
    """
    Transcribe a saved audio file with the local Faster-Whisper model.
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
        "language_mode": TRANSCRIPTION_LANGUAGE if TRANSCRIPTION_LANGUAGE else "auto",
        "provider_model_used": f"faster-whisper:{MODEL_SIZE}"
    }


def extract_openai_transcription_text(transcription_response):
    """
    Safely extract text from the OpenAI SDK response.
    """
    if hasattr(transcription_response, "text") and transcription_response.text is not None:
        return str(transcription_response.text).strip()

    if isinstance(transcription_response, dict):
        return str(transcription_response.get("text", "")).strip()

    return str(transcription_response).strip()


def transcribe_saved_audio_openai(saved_path: str):
    """
    Transcribe a saved audio file with OpenAI's transcription API.
    """
    client = get_openai_client()
    prompt_text = build_openai_transcription_prompt()

    with open(saved_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model=OPENAI_TRANSCRIBE_MODEL,
            file=audio_file,
            response_format="json",
            language=TRANSCRIPTION_LANGUAGE,
            prompt=prompt_text
        )

    transcript_text = extract_openai_transcription_text(transcription)

    return {
        "transcript": transcript_text,
        "detected_language": TRANSCRIPTION_LANGUAGE if TRANSCRIPTION_LANGUAGE else None,
        "language_probability": None,
        "language_mode": TRANSCRIPTION_LANGUAGE if TRANSCRIPTION_LANGUAGE else "auto",
        "provider_model_used": OPENAI_TRANSCRIBE_MODEL
    }


def build_transcription_attempt(saved_path: str, provider_name: str):
    """
    Run one provider attempt and package its result in a standard structure.
    """
    audio_duration_seconds = get_audio_duration_seconds(saved_path)

    if provider_name == "local":
        transcription_result = transcribe_saved_audio_local(saved_path)
    elif provider_name == "openai":
        transcription_result = transcribe_saved_audio_openai(saved_path)
    else:
        raise ValueError(f"Unsupported provider '{provider_name}'.")

    phrase_match_result = find_best_phrase_match(
        transcription_result["transcript"],
        default_minimum_score=DEFAULT_MATCH_MINIMUM_SCORE
    )

    estimated_cost_usd = 0.0
    if provider_name == "openai":
        estimated_cost_usd = estimate_openai_transcription_cost_usd(
            audio_duration_seconds,
            transcription_result["provider_model_used"]
        ) or 0.0

    return {
        "provider": provider_name,
        "audio_duration_seconds": audio_duration_seconds,
        "estimated_cost_usd": estimated_cost_usd,
        "transcription_result": transcription_result,
        "phrase_match": phrase_match_result
    }


def should_fallback_to_openai(local_attempt: dict):
    """
    Decide whether "auto" mode should call OpenAI after local Whisper.

    We fallback when the local result looks weak or borderline.
    """
    transcript_text = local_attempt["transcription_result"]["transcript"]
    phrase_match = local_attempt["phrase_match"]

    if not transcript_text:
        return True, "Local transcript was empty."

    if not phrase_match["matched"]:
        return True, "Local transcript did not confidently match a phrase."

    # If the score only barely clears the phrase threshold, get a second opinion
    if phrase_match["score"] < (phrase_match["used_minimum_score"] + AUTO_FALLBACK_SCORE_MARGIN):
        return True, "Local phrase score was too close to the threshold."

    return False, None


def choose_better_attempt(local_attempt: dict, openai_attempt: dict):
    """
    Compare local and OpenAI attempts and keep the better final result.
    """
    local_match = local_attempt["phrase_match"]
    openai_match = openai_attempt["phrase_match"]

    # OpenAI found a confident phrase match and local did not
    if openai_match["matched"] and not local_match["matched"]:
        return openai_attempt, "OpenAI matched a phrase while local did not."

    # Both matched, but OpenAI is meaningfully stronger
    if openai_match["matched"] and local_match["matched"]:
        if openai_match["score"] > (local_match["score"] + OPENAI_PROVIDER_SWITCH_SCORE_MARGIN):
            return openai_attempt, "OpenAI produced a meaningfully stronger phrase match."

    # If local is empty or much weaker, prefer OpenAI
    local_text = local_attempt["transcription_result"]["transcript"]
    openai_text = openai_attempt["transcription_result"]["transcript"]

    if not local_text and openai_text:
        return openai_attempt, "OpenAI produced a transcript while local was empty."

    if openai_match["score"] > (local_match["score"] + 8.0):
        return openai_attempt, "OpenAI produced a much stronger phrase score."

    # Otherwise keep local
    return local_attempt, "Local result was kept after comparison."


def serialize_attempt(attempt: dict):
    """
    Convert an attempt into a JSON-friendly summary.
    """
    return {
        "provider": attempt["provider"],
        "provider_model_used": attempt["transcription_result"]["provider_model_used"],
        "audio_duration_seconds": round_optional(attempt["audio_duration_seconds"], 3),
        "estimated_cost_usd": round_optional(attempt["estimated_cost_usd"], 6),
        "transcript": attempt["transcription_result"]["transcript"],
        "phrase_match": attempt["phrase_match"]
    }


def run_transcription_pipeline(saved_path: str, provider: str, include_debug_scores: bool = False):
    """
    Run the provider pipeline.

    Modes:
    - local: local Faster-Whisper only
    - openai: OpenAI only
    - auto: local first, then OpenAI fallback if needed
    """
    provider_requested = normalize_transcription_provider(provider)
    attempts = []
    fallback_used = False
    fallback_reason = None

    if provider_requested == "local":
        chosen_attempt = build_transcription_attempt(saved_path, "local")
        attempts.append(chosen_attempt)

    elif provider_requested == "openai":
        chosen_attempt = build_transcription_attempt(saved_path, "openai")
        attempts.append(chosen_attempt)

    else:
        # AUTO MODE
        local_attempt = build_transcription_attempt(saved_path, "local")
        attempts.append(local_attempt)

        should_fallback, fallback_reason = should_fallback_to_openai(local_attempt)
        chosen_attempt = local_attempt

        if should_fallback:
            try:
                openai_attempt = build_transcription_attempt(saved_path, "openai")
                attempts.append(openai_attempt)
                fallback_used = True

                chosen_attempt, comparison_reason = choose_better_attempt(local_attempt, openai_attempt)

                if fallback_reason:
                    fallback_reason = f"{fallback_reason} {comparison_reason}"
                else:
                    fallback_reason = comparison_reason

            except Exception as exc:
                # Auto mode should still work even if OpenAI is unavailable.
                fallback_used = False
                if fallback_reason:
                    fallback_reason = f"{fallback_reason} OpenAI fallback unavailable: {str(exc)}"
                else:
                    fallback_reason = f"OpenAI fallback unavailable: {str(exc)}"

    chosen_transcription = chosen_attempt["transcription_result"]
    chosen_phrase_match = chosen_attempt["phrase_match"]

    total_estimated_cost_usd = 0.0
    for attempt in attempts:
        total_estimated_cost_usd += attempt["estimated_cost_usd"] or 0.0

    output_decision = build_output_decision(chosen_phrase_match)

    response = {
        "transcript": chosen_transcription["transcript"],
        "detected_language": chosen_transcription["detected_language"],
        "language_probability": chosen_transcription["language_probability"],
        "language_mode": chosen_transcription["language_mode"],
        "provider_requested": provider_requested,
        "provider_used": chosen_attempt["provider"],
        "provider_model_used": chosen_transcription["provider_model_used"],
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "default_match_threshold": DEFAULT_MATCH_MINIMUM_SCORE,
        "audio_duration_seconds": round_optional(chosen_attempt["audio_duration_seconds"], 3),
        "cost_estimate_usd": round_optional(total_estimated_cost_usd, 6),
        "phrase_match": chosen_phrase_match,
        "output_decision": output_decision,
        "transcription_attempts": [serialize_attempt(attempt) for attempt in attempts]
    }

    if include_debug_scores:
        response["debug_scores"] = get_phrase_debug_scores(
            chosen_transcription["transcript"],
            default_minimum_score=DEFAULT_MATCH_MINIMUM_SCORE
        )

    return response

def build_output_decision(phrase_match: dict):
    """
    Build a clear final output decision for the frontend.

    Current modes:
    - replay_clip   -> use the real saved phrase clip
    - generate_voice -> no saved clip should be replayed, so a future
                        voice-generation step should handle the output
    """
    if phrase_match["matched"] and phrase_match["clip_exists"] and phrase_match["clip_url"]:
        matched_phrase = phrase_match.get("matched_phrase")

        return {
            "output_mode": "replay_clip",
            "output_clip_url": phrase_match["clip_url"],
            "output_phrase_id": matched_phrase["id"] if matched_phrase else None,
            "output_phrase_alias": phrase_match.get("matched_alias")
        }

    return {
        "output_mode": "generate_voice",
        "output_clip_url": None,
        "output_phrase_id": None,
        "output_phrase_alias": None
    }


async def transcribe_uploaded_audio(file: UploadFile, provider: str = "auto"):
    """
    Save uploaded audio and transcribe it using the requested provider mode.
    """
    saved_file_info = await save_uploaded_audio(file)
    transcription_pipeline_result = run_transcription_pipeline(
        saved_file_info["saved_path"],
        provider=provider,
        include_debug_scores=False
    )

    return {
        "message": "Audio uploaded and transcribed successfully",
        **transcription_pipeline_result,
        "file_info": saved_file_info
    }


async def transcribe_and_match_audio(file: UploadFile, provider: str = "auto"):
    """
    Save uploaded audio, transcribe it, and return phrase matching result.
    """
    saved_file_info = await save_uploaded_audio(file)
    transcription_pipeline_result = run_transcription_pipeline(
        saved_file_info["saved_path"],
        provider=provider,
        include_debug_scores=False
    )

    return {
        "message": "Audio uploaded, transcribed, and checked for phrase match",
        **transcription_pipeline_result,
        "file_info": saved_file_info
    }


async def transcribe_and_debug_match_audio(file: UploadFile, provider: str = "auto"):
    """
    Save uploaded audio, transcribe it, and return phrase matching + debug details.
    """
    saved_file_info = await save_uploaded_audio(file)
    transcription_pipeline_result = run_transcription_pipeline(
        saved_file_info["saved_path"],
        provider=provider,
        include_debug_scores=True
    )

    return {
        "message": "Audio uploaded, transcribed, and debug phrase scores generated",
        **transcription_pipeline_result,
        "file_info": saved_file_info
    }