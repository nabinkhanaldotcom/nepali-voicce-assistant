# # app/main.py
# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
#
# from app.api.v1.stt_tts import router as stt_tts_router
#
#
# app = FastAPI(
#     title="Nepali Voice Assistant",
#     version="0.1.0",
# )
#
# # Allow your Angular app to call this backend
# origins = [
#     "http://localhost:4200",
# ]
#
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
#
#
# @app.get("/health")
# def health():
#     return {"status": "ok"}
#
#
# # Register our routes (like @RequestMapping controllers in Spring)
# app.include_router(stt_tts_router)
# # If you want prefix like /api/v1: use app.include_router(stt_tts_router, prefix="/api/v1")
