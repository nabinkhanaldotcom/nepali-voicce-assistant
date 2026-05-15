# Nepali Voice Matcher

This project is a browser-based Nepali voice matching app.

Current flow:
1. Record audio in the browser OR choose an audio file from your computer
2. Send audio to the Python backend
3. Transcribe speech with Faster-Whisper
4. Compare the transcript against known Nepali phrase aliases
5. If a phrase clip exists, return its clip URL

---

## 1. Clone the repo

```bash
git clone <YOUR_REPO_URL>
cd nepali-voicce-assistant
```

cd backend_api

# Create a virtual environment
python3.11 -m venv venv

# Activate it (macOS / Linux)
source venv/bin/activate

# Install backend packages
pip install -r requirements.txt

# Run the FastAPI server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000




cd frontend/nepali-voice-ui

# Install frontend packages
npm install

# Start Angular dev server
npm start