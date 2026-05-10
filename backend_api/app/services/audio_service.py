from pathlib import Path
from uuid import uuid4
from fastapi import UploadFile, HTTPException

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}


async def save_uploaded_audio(file: UploadFile):
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


async def fake_transcribe_audio(file: UploadFile):
    saved_file_info = await save_uploaded_audio(file)

    fake_transcript = (
        "This is a fake transcription for now. "
        "Later we will replace this with real speech-to-text."
    )

    return {
        "message": "Audio uploaded and processed successfully",
        "transcript": fake_transcript,
        "file_info": saved_file_info
    }