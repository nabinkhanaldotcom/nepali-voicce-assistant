# backend_api/app/main.py
#
# This is the main entry point for the FastAPI backend.
#
# Think of this like the "main Spring Boot application class" in Java:
# - it creates the FastAPI app
# - it configures CORS so Angular can call the backend
# - it serves static phrase clips from /phrase-clips
# - it registers route files such as app/routes/audio.py

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routes.audio import router as audio_router

app = FastAPI(title="Nepali Voice Transcription / Voice Override API")

# Angular runs on port 4200 during development.
# Without CORS, the browser would block Angular from calling FastAPI.
origins = [
    "http://localhost:4200",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# backend_api folder
BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Saved phrase clips live here:
# backend_api/phrase_clips/abuiiiAbuiii.m4a
PHRASE_CLIPS_DIR = BACKEND_ROOT / "phrase_clips"
PHRASE_CLIPS_DIR.mkdir(parents=True, exist_ok=True)

# This makes phrase clips playable from the browser.
#
# Example:
# http://localhost:8000/phrase-clips/abuiiiAbuiii.m4a
app.mount(
    "/phrase-clips",
    StaticFiles(directory=str(PHRASE_CLIPS_DIR)),
    name="phrase-clips",
)

# Register audio endpoints:
# POST /upload-audio
# POST /transcribe-audio
# POST /transcribe-and-match
app.include_router(audio_router)


@app.get("/")
def home():
    return {
        "message": "Backend is running",
        "project": "Nepali Voice Transcription / Voice Override",
    }


@app.get("/health")
def health():
    return {"status": "ok"}