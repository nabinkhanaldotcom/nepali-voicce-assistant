# # This endpoint will:
# #
# # accept an uploaded audio file
# # check whether it looks like audio
# # save it into an uploads folder
# # return information about the file
#
# from fastapi import FastAPI, UploadFile, File, HTTPException
# from pydantic import BaseModel
# from pathlib import Path
# from uuid import uuid4
#
# app = FastAPI()
#
# # This creates a folder named "uploads" inside backend_api if it does not already exist
# UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
# UPLOAD_DIR.mkdir(exist_ok=True)
#
# @app.post("/upload-audio")
# async def upload_audio(file: UploadFile = File(...)):
#     if not file.filename:
#         raise HTTPException(status_code=400, detail="No file name was provided")
#
#     allowed_extensions = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}
#     file_extension = Path(file.filename).suffix.lower()
#
#     if file_extension not in allowed_extensions:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Unsupported file type. Allowed types: {sorted(allowed_extensions)}"
#         )
#
#     unique_name = f"{uuid4()}{file_extension}"
#     saved_file_path = UPLOAD_DIR / unique_name
#
#     file_bytes = await file.read()
#     saved_file_path.write_bytes(file_bytes)
#
#     return {
#         "message": "Audio uploaded successfully",
#         "original_filename": file.filename,
#         "saved_filename": unique_name,
#         "content_type": file.content_type,
#         "size_in_bytes": len(file_bytes),
#         "saved_path": str(saved_file_path)
#     }