This is for local: it is complete to record and replay the audio
for this,
Make sure your venv is active:

cd /Users/mario/myFolder/voice-clone-app/nepali-voicce-assistant/backend
source venv/bin/activate

Ensure faster-whisper is installed:

pip install faster-whisper

Run the backend:

uvicorn main:app --reload --host 0.0.0.0 --port 8000
First run will download the "medium" model; it might take a bit.
Watch the logs: you should see [INFO] Faster-Whisper model ready. and [STT] Transcribing file ... messages.
Go to your Angular UI (ng serve already running → http://localhost:4200):
Record a Nepali sentence.
Stop.
Click Send Recording to STT.
See how much the transcription improved.
A couple of notes
If your Mac runs out of RAM or becomes very slow:
Change model_size from "medium" to "small" in create_whisper_model().
If int8_float16 fails on your CPU:
The code already falls back to compute_type="int8" and logs a warning.
If later you want even more quality:
You can try "large-v3" on a more powerful machine (not recommended on older MacBooks though).

******************************************************
notes:
source venv/bin/activate i did this, now how to get out of this?
deactivate

So the usual backend pattern is:
-------------------------------
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# ... work ...
deactivate
-------------------------------
source venv/bin/activate   # macOS / Linux
# (You should now see (venv) at the start of your prompt)

Double check that this venv is really using 3.11:

python --version

You should see: Python 3.11.x
If it still says 3.13, something is off (e.g., wrong python path); but if it’s 3.11, you’re good.

4️⃣ Reinstall backend dependencies inside this new venv

Still in backend with (venv) active:

pip install --upgrade pip setuptools wheel
pip install fastapi uvicorn[standard] python-multipart
pip install openai-whisper

***
    🔁 New plan (still free, still local, but avoids llvmlite)

Instead of:

openai-whisper (which depends on numba → llvmlite → LLVM hell)

We’ll use:

faster-whisper – a CTranslate2-based Whisper implementation
No llvmlite
No numba
Works great on CPU-only machines
Still free and local

Your Angular frontend stays exactly the same. We only change the backend.

1️⃣ Clean up broken Whisper attempt

In your backend venv, from the backend folder:

cd /Users/mario/myFolder/voice-clone-app/nepali-voicce-assistant/backend
source venv/bin/activate   # make sure (venv) shows

# Remove partial/broken installs if they got pulled in
pip uninstall -y openai-whisper numba llvmlite

(This is just to avoid pip trying to reuse half-broken installs.)

2️⃣ Install faster-whisper instead

Still inside the venv:

pip install faster-whisper
***

removing everything we did for this project install

# 1. In your project backend
cd /Users/mario/myFolder/voice-clone-app/nepali-voicce-assistant/backend
rm -rf venv

# 2. Clear Python caches & model caches (user-level)
rm -rf ~/.cache/pip
rm -rf ~/.cache/huggingface
rm -rf ~/.cache/ctranslate2
rm -rf ~/.cache/whisper

# 3. Remove heavy brew formulae we pulled for STT/ffmpeg
brew uninstall python@3.14 icu4c@78 boost source-highlight asciidoc docbook-xsl bison doxygen ffmpeg
brew cleanup
rm -rf ~/Library/Caches/Homebrew