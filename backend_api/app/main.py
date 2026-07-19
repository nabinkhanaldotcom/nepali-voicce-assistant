# backend_api/app/main.py
#
# This is the main entry point for the FastAPI backend.
#
# Think of this like the "main Spring Boot application class" in Java:
# - it creates the FastAPI app
# - it configures CORS so Angular can call the backend
# - it serves static phrase clips from /phrase-clips
# - it registers route files such as app/routes/auth.py, audio.py, and rvc.py
# - it adds basic security response headers

from pathlib import Path
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routes.auth import router as auth_router
from app.routes.audio import router as audio_router
from app.routes.rvc import router as rvc_router


app = FastAPI(title="Nepali Voice Transcription / Artist Voice Override API")


def get_allowed_origins() -> list[str]:
    """
    Read allowed frontend origins from environment variable.

    Local default:
      http://localhost:4200

    Production example:
      ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
    """
    origins_value = os.getenv("ALLOWED_ORIGINS", "http://localhost:4200")

    return [
        origin.strip()
        for origin in origins_value.split(",")
        if origin.strip()
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Add basic security headers.

    These do not replace Nginx/Caddy/HTTPS security,
    but they are a good baseline for the FastAPI app.
    """
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Enable this in production only when the site is served through HTTPS.
    #
    # Example:
    # ENABLE_HSTS=true
    if os.getenv("ENABLE_HSTS", "false").lower() == "true":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response


# backend_api folder
BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Saved phrase clips live here:
# backend_api/phrase_clips/abuiiiAbuiii.m4a
PHRASE_CLIPS_DIR = BACKEND_ROOT / "phrase_clips"
PHRASE_CLIPS_DIR.mkdir(parents=True, exist_ok=True)

# Note:
# This static folder is still public if someone knows the clip URL.
# The expensive/private API actions are protected by login.
#
# Later, if you want phrase clips protected too, replace this static mount
# with a protected endpoint that returns FileResponse after token validation.
app.mount(
    "/phrase-clips",
    StaticFiles(directory=str(PHRASE_CLIPS_DIR)),
    name="phrase-clips",
)

# Public auth endpoint:
# POST /auth/login
# GET /auth/me requires token
app.include_router(auth_router)

# Protected audio endpoints:
# POST /upload-audio
# POST /transcribe-audio
# POST /transcribe-and-match
# POST /convert-audio-download
app.include_router(audio_router)

# Protected RVC voice generation endpoint:
# POST /generate-voice
app.include_router(rvc_router)


@app.get("/")
def home():
    return {
        "message": "Backend is running",
        "project": "Nepali Voice Transcription / Artist Voice Override",
    }


@app.get("/health")
def health():
    return {"status": "ok"}