 # Uncle Voice Dataset Preparation

This folder is for preparing uncle-style voice data for future voice conversion training.

## Goal

The long-term app goal is not just to play saved phrase clips.

The real goal is:

1. User records or uploads speech.
2. The app transcribes the speech.
3. A future voice conversion model converts the user's speech into an uncle-like comedic voice/style.
4. Tone presets such as `original`, `happy`, `sad`, and `punchline` should eventually affect the generated output.

This folder prepares the training/reference data needed for that future voice conversion model.

## Important idea

Voice conversion is different from text-to-speech.

### Text-to-speech

Text-to-speech usually means:

```text
text
  ↓
generated audio