from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from faster_whisper import WhisperModel

import io
import wave
import tempfile
import os
import sys

app = FastAPI()

# --- CORS so Angular (http://localhost:4200) can call us ---
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


@app.get("/health")
def health():
    return {"status": "ok"}


# --- Load Faster-Whisper model once at startup ---

def create_whisper_model() -> WhisperModel:
    """
    Try a higher-quality config first (medium, int8_float16).
    If that fails (e.g., unsupported compute_type), fall back to int8.
    """
    model_size = "medium"  # you can change to "small" if this is too slow / heavy

    try:
        print(
            f"Loading Faster-Whisper model '{model_size}' "
            f"with compute_type='int8_float16' on CPU...",
            file=sys.stderr,
        )
        return WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8_float16",   # better quality than pure int8
        )
    except Exception as e:
        print(
            f"[WARN] Failed to load with int8_float16 ({e}). "
            f"Falling back to compute_type='int8'.",
            file=sys.stderr,
        )
        return WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",          # slower? not much; still decent
        )


whisper_model = create_whisper_model()
print("[INFO] Faster-Whisper model ready.", file=sys.stderr)


# --- STT: accepts audio file, returns recognized Nepali text ---
@app.post("/stt")
async def stt(audio: UploadFile = File(...)):
    # Save uploaded file to a temporary path
    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file_bytes = await audio.read()
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # Transcribe with Faster-Whisper
        # language="ne" => force Nepali (your request)
        # beam_size=8   => better quality vs beam_size=1, at cost of speed
        print(f"[STT] Transcribing file {tmp_path} ...", file=sys.stderr)
        # This wisper.model.transcribe is the one that runs locally. this is what is changed if api is used instead of local
        segments, info = whisper_model.transcribe(
            tmp_path,
            language="ne",
            beam_size=8,
        )
        print(
            f"[STT] Done. Language={info.language}, prob={info.language_probability:.3f}",
            file=sys.stderr,
        )

        # Collect all segments into a single string
        text_parts = []
        for seg in segments:
            # seg.text often has leading spaces; strip them
            text_parts.append(seg.text.strip())

        full_text = " ".join(text_parts).strip()
        if not full_text:
            full_text = "Could not understand audio."

        return {"text": full_text}
    except Exception as e:
        print("STT error:", e, file=sys.stderr)
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to transcribe audio."}
        )
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# --- TTS: still dummy 1-second silent WAV for now ---
@app.post("/tts")
async def tts(payload: dict):
    text = payload.get("text", "")

    # For now we ignore the text and return 1 second of silence.
    # Later, you will replace this with a real TTS engine.
    sample_rate = 16000
    duration_seconds = 1
    num_samples = sample_rate * duration_seconds

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_samples)

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="audio/wav",
        headers={"Content-Disposition": 'inline; filename="tts_output.wav"'}
    )
