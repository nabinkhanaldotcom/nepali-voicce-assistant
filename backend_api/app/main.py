from fastapi import FastAPI
from app.routes.audio import router as audio_router

app = FastAPI()

app.include_router(audio_router)


@app.get("/")
def home():
    return {"message": "Backend is running"}


@app.get("/health")
def health():
    return {"status": "ok"}