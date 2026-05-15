from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.audio import router as audio_router

app = FastAPI()

PHRASE_CLIPS_DIR = Path(__file__).resolve().parent.parent / "phrase_clips"
PHRASE_CLIPS_DIR.mkdir(exist_ok=True)

app.mount("/phrase-clips", StaticFiles(directory=str(PHRASE_CLIPS_DIR)), name="phrase-clips")

app.include_router(audio_router)


@app.get("/")
def home():
    return {"message": "Backend is running"}


@app.get("/health")
def health():
    return {"status": "ok"}