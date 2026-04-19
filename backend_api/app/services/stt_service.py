# app/services/stt_service.py

import os
import tempfile
from typing import Optional

from fastapi import UploadFile
from openai import OpenAI


# Single shared OpenAI client (like a Spring bean)
client = OpenAI()

# Read API key from env var: OPENAI_API_KEY
# Set it in your shell before running uvicorn:
#   export OPENAI_API_KEY="sk-..."
# The OpenAI client automatically uses it.


async def transcribe_nepali(upload_file: UploadFile) -> str:
    """
    Take an uploaded audio file (from FastAPI),
    send it to OpenAI STT, and return the recognized text.
    This is analogous to a Spring @Service method.
    """

    # 1) Save UploadFile to a temporary file;
    #    OpenAI API expects a file-like object.
    suffix = os.path.splitext(upload_file.filename or "")[1] or ".webm"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file_bytes = await upload_file.read()
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # 2) Open the temp file and call OpenAI STT
        with open(tmp_path, "rb") as audio_file:
            # Model: gpt-4o-mini-transcribe is good & cheaper.
            # You can change this later if needed.
            response = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file,
                language="ne",  # hint: Nepali speech
            )

        # 3) Extract text from response
        text: Optional[str] = getattr(response, "text", None)
        if text:
            text = text.strip()

        if not text:
            text = "Could not understand audio."

        return text

    finally:
        # 4) Always remove temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
