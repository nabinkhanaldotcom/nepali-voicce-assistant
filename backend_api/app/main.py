# backend_api/app/main.py
#
# Main entry point for the FastAPI backend.

from pathlib import Path
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routes.auth import router as auth_router
from app.routes.audio import router as audio_router
from app.routes.rvc import router as rvc_router
from app.routes.usage import router as usage_router
from app.services.usage_metrics_service import initialize_usage_metrics_database

app = FastAPI(title="Nepali Voice Transcription / Artist Voice Override API")


def get_allowed_origins() -> list[str]:
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
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-API-Key",
        "X-Usage-Admin-Token",
    ],
)


@app.on_event("startup")
async def startup_event():
    initialize_usage_metrics_database()


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    if os.getenv("ENABLE_HSTS", "false").lower() == "true":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response


BACKEND_ROOT = Path(__file__).resolve().parent.parent

PHRASE_CLIPS_DIR = BACKEND_ROOT / "phrase_clips"
PHRASE_CLIPS_DIR.mkdir(parents=True, exist_ok=True)

app.mount(
    "/phrase-clips",
    StaticFiles(directory=str(PHRASE_CLIPS_DIR)),
    name="phrase-clips",
)

app.include_router(auth_router)
app.include_router(audio_router)
app.include_router(rvc_router)
app.include_router(usage_router)


@app.get("/")
def home():
    return {
        "message": "Backend is running",
        "project": "Nepali Voice Transcription / Artist Voice Override",
    }


@app.get("/health")
def health():
    return {"status": "ok"}