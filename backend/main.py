from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/stt")
async def stt(audio: UploadFile = File(...)):
    # TODO: save audio, call STT, return text
    return {"text": "dummy nepali text"}

@app.post("/tts")
async def tts(payload: dict):
    text = payload["text"]
    # TODO: call TTS, save to file
    # Return file or bytes
    return FileResponse("output.wav", media_type="audio/wav")
