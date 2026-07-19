# Nepali Voice Assistant - Phase 3: Local RVC Artist Voice Generation

This README documents Phase 3 of the Nepali Voice Assistant project.

Phase 3 connects the trained RVC voice model to the local FastAPI backend and Angular frontend so the app can generate Artist's Voice audio from recorded or uploaded audio.

---

## Current Phase 3 Status

Completed and tested locally:

```text
Phase 3A: Manual RVC command works
Phase 3B: RVC wrapper script works
Phase 3C: FastAPI /generate-voice endpoint works
Phase 3D: Angular Generate Artist's Voice button works
Phase 3E: 60-second recording limit and safer backend upload validation added
```

Known working branch:

```text
phase-3
```

Important commits already pushed on `phase-3`:

```text
7a7775f9 - adding ui changes for generating voice
58dcf41 - Adding FastAPI RVC voice generation endpoint
3e5a863 - Add local RVC inference wrapper
9364fb4 - fixing download options menu for recorded audio
ac377aa - adding ui cleanup and added option to download recorded voice in various format
```

---

## What Phase 3 Adds

Before Phase 3, the app could:

```text
record audio
upload audio
transcribe audio
match saved Nepali phrase clips
download audio in multiple formats
```

Phase 3 adds the local RVC Artist's Voice conversion flow:

```text
record/upload audio
        ↓
send audio to FastAPI
        ↓
validate file size, file type, audio-only streams, and duration
        ↓
convert audio to clean WAV using ffmpeg
        ↓
call local RVC Python environment
        ↓
use trained .pth model + .index file
        ↓
return generated WAV audio
        ↓
play/download generated Artist's Voice in Angular
```

---

## Current Safety Limits

Frontend:

```text
Maximum browser recording length: 60 seconds
```

Backend:

```text
Maximum accepted audio duration: 65 seconds
Maximum upload size: 25 MB
Only one file is accepted per /generate-voice request
Only allowlisted audio extensions are accepted
ffprobe must validate the uploaded file as audio-only
ffmpeg converts the input into a clean WAV before RVC
RVC subprocess has a timeout
temporary upload/input files are deleted after processing
generated output file is deleted after response is sent
```

The backend allows 65 seconds instead of exactly 60 seconds because encoded browser audio can sometimes be slightly longer than the visible recording timer.

---

## High-Level Architecture

```text
Angular UI
  |
  | POST /generate-voice
  | multipart/form-data
  |
FastAPI backend
  |
  | requires exactly one file
  | validates extension/content type
  | saves uploaded audio with UUID filename
  | validates audio with ffprobe
  | converts input to WAV using ffmpeg
  |
RVC wrapper script
  |
  | called using backend_api/.venv-rvc/Scripts/python.exe
  |
Trained RVC model
  |
  | hari_normal_v1_100e_11100s.pth
  | hari_normal_v1.index
  |
Generated WAV output
  |
  | returned to Angular
  |
Browser audio player
```

---

## Important Project Folders

```text
nepali-voicce-assistant/
  backend_api/
    app/
      main.py
      routes/
        audio.py
        rvc.py
      services/
        audio_service.py
        rvc_generation_service.py

    rvc_engine/
      run_rvc_inference.py

    models/
      rvc/
        hari_normal_v1/
          hari_normal_v1_100e_11100s.pth
          hari_normal_v1.index

    data/
      rvc_test_inputs/
      rvc_generated_inputs/

    uploads/
      rvc_generation/

    outputs/
      rvc/

    .venv/
    .venv-rvc/

  frontend/
    nepali-voice-ui/
      src/app/services/voice.service.ts
      src/app/components/voice-console/
        voice-console.component.ts
        voice-console.component.html
        voice-console.component.scss
```

---

## Important Local Files Not Committed to Git

These files/folders should stay local and should not be committed:

```text
backend_api/.venv-rvc/
backend_api/models/
backend_api/data/rvc_test_inputs/
backend_api/data/rvc_generated_inputs/
backend_api/uploads/rvc_generation/
backend_api/outputs/rvc/
*.pth
*.index
*.zip
```

Reason:

```text
.venv-rvc is very large
model files are very large
test audio files are local/generated
generated output audio files are local/generated
```

The `.gitignore` should include:

```gitignore
# Local trained voice models
backend_api/models/
*.pth
*.index
*.zip

# Local RVC test files and generated outputs
backend_api/data/rvc_test_inputs/
backend_api/outputs/rvc/

# RVC local virtual environment
backend_api/.venv-rvc/

# Local RVC generated input files
backend_api/data/rvc_generated_inputs/
backend_api/uploads/rvc_generation/
```

---

## Python Environments

Phase 3 uses two separate Python virtual environments.

### 1. Normal backend environment

Path:

```text
backend_api/.venv
```

Purpose:

```text
FastAPI
Whisper transcription
OpenAI transcription
phrase matching
audio upload
audio download conversion
normal backend routes
```

Use this environment to run FastAPI.

### 2. RVC-only environment

Path:

```text
backend_api/.venv-rvc
```

Purpose:

```text
rvc-python
torch
fairseq
rmvpe
faiss
RVC conversion dependencies
```

This environment is used only for voice conversion.

FastAPI does not import `rvc-python` directly. Instead, FastAPI calls:

```text
backend_api/.venv-rvc/Scripts/python.exe
```

and that Python runs:

```text
backend_api/rvc_engine/run_rvc_inference.py
```

This keeps the normal backend stable and avoids mixing heavy RVC dependencies with the transcription backend.

---

## Backend Requirements

Normal FastAPI backend dependencies are in:

```text
backend_api/requirements.txt
```

Current expected contents:

```txt
fastapi==0.128.0
uvicorn==0.40.0
python-multipart==0.0.21
python-dotenv
openai
faster-whisper
rapidfuzz
av
```

RVC dependencies are intentionally not in this file.

---

## Required RVC Model Files

The trained RVC model files must exist locally here:

```text
backend_api/models/rvc/hari_normal_v1/hari_normal_v1_100e_11100s.pth
backend_api/models/rvc/hari_normal_v1/hari_normal_v1.index
```

These files are not committed to Git.

---

## /generate-voice Endpoint

Backend endpoint:

```text
POST /generate-voice
```

Request type:

```text
multipart/form-data
```

Fields:

```text
file       required, exactly one audio file
pitch      optional, default 6
indexRate  optional, default 0.75
protect    optional, default 0.5
method     optional, default rmvpe
```

Recommended default values:

```text
pitch: 6
indexRate: 0.75
protect: 0.5
method: rmvpe
```

Other pitch values to test:

```text
0
4
6
8
10
```

Allowed RVC methods:

```text
rmvpe
harvest
crepe
pm
```

The endpoint returns:

```text
audio/wav
```

---

## Run FastAPI for RVC Testing

Important: run FastAPI without `--reload` during RVC testing.

```powershell
cd "C:\AI app\nepali-voicce-assistant\backend_api"

.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Do not use this for RVC testing yet:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Reason:

```text
--reload watches files inside backend_api.
Because .venv-rvc is also inside backend_api, RVC may touch files inside .venv-rvc.
That can cause FastAPI to restart during voice generation.
```

---

## Test /generate-voice With curl

Open a second PowerShell terminal while FastAPI is running.

```powershell
curl.exe -X POST "http://localhost:8000/generate-voice" `
  -F "file=@C:\AI app\nepali-voicce-assistant\backend_api\data\rvc_test_inputs\recording.weba" `
  -F "pitch=6" `
  -F "indexRate=0.75" `
  -F "protect=0.5" `
  -F "method=rmvpe" `
  --output "C:\AI app\nepali-voicce-assistant\backend_api\outputs\rvc\api_generated_voice.wav"
```

Play the generated file:

```powershell
Start-Process "C:\AI app\nepali-voicce-assistant\backend_api\outputs\rvc\api_generated_voice.wav"
```

---

## Run Angular

Start the backend first:

```powershell
cd "C:\AI app\nepali-voicce-assistant\backend_api"

.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then start Angular in another terminal:

```powershell
cd "C:\AI app\nepali-voicce-assistant\frontend\nepali-voice-ui"

npm start
```

Then open:

```text
http://localhost:4200
```

---

## Browser Test Flow

```text
1. Open Angular app.
2. Record audio or choose one audio file.
3. Recording automatically stops after 60 seconds.
4. Play preview audio to confirm the input is correct.
5. Keep RVC settings as:
   pitch = 6
   pitch extraction = rmvpe
   search feature ratio = 0.75
   protect = 0.5
6. Click Generate Artist's Voice.
7. Wait for the generated audio section to appear.
8. Play generated voice.
9. Try Download Generated Artist's Voice.
```

Expected result:

```text
Generated Artist's Voice WAV audio should play in the browser.
```

---

## Security Measures Added

Current app-level protections:

```text
Frontend recording limit: 60 seconds
Backend duration limit: 65 seconds
Backend upload size limit: 25 MB
Exactly one uploaded file required by /generate-voice
Audio extension allowlist
Browser content type early check
ffprobe validation
Audio-only stream requirement
Video/data/subtitle streams rejected
UUID server-side filenames
Raw uploaded files are not served publicly
ffmpeg conversion to clean WAV before RVC
ffprobe validation after conversion
ffmpeg timeout
ffprobe timeout
RVC subprocess timeout
Temporary upload/input cleanup
Generated output cleanup after response
Safer CORS configuration through ALLOWED_ORIGINS
Basic security headers
```

---

## Hosting Notes

For local testing, the Angular app can use:

```text
http://localhost:4200
```

For hosting, microphone access should use HTTPS. Browsers require secure contexts for microphone access except for local development cases like localhost.

Recommended production shape:

```text
Domain
  ↓
HTTPS reverse proxy such as Nginx or Caddy
  ↓
Angular static build
  ↓
FastAPI backend on private port 8000
  ↓
RVC .venv-rvc + model files on server
```

Before public hosting, add:

```text
real login/authentication
rate limiting
request queue for RVC generation
server-side cleanup job
production logging
HTTPS only
locked CORS origins
Nginx/Caddy max upload size
Nginx/Caddy rate limits
```

---

## Environment Variables

Optional backend environment variables:

```text
ALLOWED_ORIGINS=http://localhost:4200
ENABLE_HSTS=false
RVC_PYTHON_EXE=C:\AI app\nepali-voicce-assistant\backend_api\.venv-rvc\Scripts\python.exe
MAX_RVC_UPLOAD_BYTES=26214400
MAX_RVC_DURATION_SECONDS=65
FFPROBE_TIMEOUT_SECONDS=15
FFMPEG_TIMEOUT_SECONDS=45
RVC_SUBPROCESS_TIMEOUT_SECONDS=180
```

Production example:

```text
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
ENABLE_HSTS=true
```

---

## Troubleshooting

### PowerShell cannot find backend venv

Wrong path:

```powershell
.\venv\Scripts\python.exe
```

Correct path:

```powershell
.\.venv\Scripts\python.exe
```

Correct backend activation command:

```powershell
.\.venv\Scripts\Activate.ps1
```

Correct RVC activation command:

```powershell
.\.venv-rvc\Scripts\Activate.ps1
```

---

### ffprobe or ffmpeg not found

Check:

```powershell
ffmpeg -version
ffprobe -version
```

If PowerShell does not recognize them, install ffmpeg and make sure it is available in PATH.

---

### File rejected as non-audio

The backend now checks:

```text
extension
content type
ffprobe media streams
duration
container format
```

This means renamed fake files like:

```text
script.js renamed to script.mp3
html file renamed to audio.wav
video file uploaded as webm
```

should be rejected.

---

### Audio too long

Frontend stops recording after:

```text
60 seconds
```

Backend rejects anything longer than:

```text
65 seconds
```

---

### RVC output is not close enough to target voice

RVC changes voice color/timbre, but the input speaker still controls:

```text
rhythm
pronunciation
emotion
speed
pitch shape
speaking style
```

Try different RVC settings:

```text
pitch: 0, 4, 6, 8, 10
indexRate: 0.5, 0.6, 0.75
protect: 0.33, 0.5
method: rmvpe
```

For better voice similarity, speak closer to the target delivery style.

---

## Suggested Commit

After applying these changes:

```powershell
cd "C:\AI app\nepali-voicce-assistant"

git status --short

git add README.md `
  backend_api/requirements.txt `
  backend_api/app/main.py `
  backend_api/app/routes/rvc.py `
  backend_api/app/services/rvc_generation_service.py `
  frontend/nepali-voice-ui/src/app/services/voice.service.ts `
  frontend/nepali-voice-ui/src/app/components/voice-console/voice-console.component.ts `
  frontend/nepali-voice-ui/src/app/components/voice-console/voice-console.component.html

git commit -m "Add recording limits and secure Artist Voice upload validation"
```

---

## Phase 3 Summary

Phase 3 successfully connects the trained local RVC model to the app.

Final working flow:

```text
User records/uploads audio in Angular
        ↓
Angular sends one audio file to FastAPI /generate-voice
        ↓
FastAPI validates size, duration, extension, content type, and audio-only streams
        ↓
FastAPI saves uploaded audio with a safe UUID filename
        ↓
FastAPI converts audio to clean WAV using ffmpeg
        ↓
FastAPI calls .venv-rvc Python
        ↓
RVC wrapper uses hari_normal_v1 .pth + .index
        ↓
Generated WAV is returned to Angular
        ↓
Temporary server files are cleaned up
        ↓
User can play/download generated Artist's Voice
```

This completes the first working end-to-end local Artist Voice conversion flow for the Nepali Voice Assistant project.