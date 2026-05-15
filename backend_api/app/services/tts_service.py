# # app/services/tts_service.py
#
# import io
# import wave
# from fastapi.responses import StreamingResponse
#
#
# def synthesize_dummy_wav(text: str) -> StreamingResponse:
#     """
#     Dummy TTS: return 1 second of silence as WAV.
#     You will replace this with real TTS later.
#     """
#
#     sample_rate = 16000
#     duration_seconds = 1
#     num_samples = sample_rate * duration_seconds
#
#     buffer = io.BytesIO()
#     with wave.open(buffer, "wb") as wf:
#         wf.setnchannels(1)
#         wf.setsampwidth(2)  # 16-bit
#         wf.setframerate(sample_rate)
#         wf.writeframes(b"\x00\x00" * num_samples)
#
#     buffer.seek(0)
#
#     return StreamingResponse(
#         buffer,
#         media_type="audio/wav",
#         headers={"Content-Disposition": 'inline; filename=\"tts_output.wav\"'},
#     )
