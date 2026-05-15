// frontend/nepali-voice-ui/src/app/components/voice-console/voice-console.component.ts

// This component controls the UI page.
// It can:
// 1. record audio from the microphone
// 2. let the user pick an audio file from the computer
// 3. send the audio to the backend
// 4. show transcript + phrase match result
// 5. play the matched phrase clip if one exists

import { Component, NgZone, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  VoiceService,
  TranscribeAndMatchResponse
} from '../../services/voice.service';

@Component({
  selector: 'app-voice-console',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './voice-console.component.html',
  styleUrl: './voice-console.component.scss'
})
export class VoiceConsoleComponent implements OnDestroy {
  // UI states
  isRecording = false;
  isProcessing = false;

  // Transcription / error state
  recognizedText = '';
  errorMessage = '';

  // Language info returned by backend
  detectedLanguage = '';
  languageProbability: number | null = null;
  languageMode = '';

  // Phrase match result returned by backend
  matchFound = false;
  matchScore: number | null = null;
  matchedPhraseText = '';
  matchedClipUrl: string | null = null;
  matchedClipExists = false;

  // Track whether current audio came from microphone or file picker
  selectedInputType: 'recording' | 'file' | null = null;
  selectedAudioName = '';

  // MediaRecorder-related state
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];

  // The currently selected audio (recorded or chosen file)
  lastAudioBlob: Blob | null = null;
  recordedAudioUrl: string | null = null;

  constructor(
    private voiceService: VoiceService,
    private ngZone: NgZone
  ) {}

  /**
   * Start recording audio from the microphone.
   */
  startRecording(): void {
    this.errorMessage = '';

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.errorMessage = 'This browser does not support microphone recording.';
      return;
    }

    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((stream: MediaStream) => {
        this.audioChunks = [];
        this.mediaRecorder = new MediaRecorder(stream);

        // Each time the recorder has a chunk, store it.
        this.mediaRecorder.ondataavailable = (event: BlobEvent) => {
          if (event.data && event.data.size > 0) {
            this.audioChunks.push(event.data);
          }
        };

        // When recording stops, combine chunks into one audio blob.
        this.mediaRecorder.onstop = () => {
          const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });

          // ngZone.run ensures Angular updates the UI properly
          this.ngZone.run(() => {
            this.setCurrentAudio(
              audioBlob,
              URL.createObjectURL(audioBlob),
              'recording',
              'recording.webm'
            );
          });
        };

        this.mediaRecorder.start();
        this.isRecording = true;
      })
      .catch((err: unknown) => {
        console.error('Microphone access error:', err);
        this.errorMessage = 'Could not access microphone. Please allow microphone permission.';
      });
  }

  /**
   * Stop microphone recording.
   */
  stopRecording(): void {
    if (this.mediaRecorder && this.isRecording) {
      this.mediaRecorder.stop();
      this.mediaRecorder.stream.getTracks().forEach((track: MediaStreamTrack) => track.stop());
      this.isRecording = false;
    }
  }

  /**
   * Called when the user chooses a file from the computer.
   */
  onFileSelected(event: Event): void {
    this.errorMessage = '';

    const input = event.target as HTMLInputElement;

    if (!input.files || input.files.length === 0) {
      return;
    }

    const selectedFile = input.files[0];

    // Basic browser-side validation
    if (!selectedFile.type.startsWith('audio/')) {
      this.errorMessage = 'Please choose a valid audio file.';
      return;
    }

    const previewUrl = URL.createObjectURL(selectedFile);

    this.setCurrentAudio(
      selectedFile,
      previewUrl,
      'file',
      selectedFile.name
    );
  }

  /**
   * Send the currently selected audio to the backend.
   */
  sendToBackend(): void {
    this.errorMessage = '';

    if (!this.lastAudioBlob) {
      this.errorMessage = 'No audio available. Please record or choose a file first.';
      return;
    }

    if (!this.selectedAudioName) {
      this.errorMessage = 'Audio file name is missing.';
      return;
    }

    this.isProcessing = true;

    this.voiceService.transcribeAndMatch(this.lastAudioBlob, this.selectedAudioName).subscribe({
      next: (res: TranscribeAndMatchResponse) => {
        this.recognizedText = res.transcript || '';
        this.detectedLanguage = res.detected_language || '';
        this.languageProbability = res.language_probability ?? null;
        this.languageMode = res.language_mode || '';

        this.matchFound = res.phrase_match?.matched ?? false;
        this.matchScore = res.phrase_match?.score ?? null;
        this.matchedPhraseText = res.phrase_match?.matched_alias ?? '';
        this.matchedClipExists = res.phrase_match?.clip_exists ?? false;
        this.matchedClipUrl = this.voiceService.getFullClipUrl(res.phrase_match?.clip_url ?? null);

        this.isProcessing = false;
      },
      error: (err: unknown) => {
        console.error('Backend error:', err);
        this.errorMessage = 'Error sending audio to the backend.';
        this.isProcessing = false;
      }
    });
  }

  /**
   * Play the matched backend clip, if one exists.
   */
  playMatchedClip(): void {
    if (!this.matchedClipUrl) {
      this.errorMessage = 'No matched clip is available.';
      return;
    }

    const audio = new Audio(this.matchedClipUrl);

    audio.play().catch((err: unknown) => {
      console.warn('Audio play error:', err);
      this.errorMessage = 'Could not play the matched clip.';
    });
  }

  /**
   * Clear the currently selected/recorded audio.
   */
  clearSelectedAudio(): void {
    this.lastAudioBlob = null;
    this.selectedInputType = null;
    this.selectedAudioName = '';

    if (this.recordedAudioUrl) {
      URL.revokeObjectURL(this.recordedAudioUrl);
      this.recordedAudioUrl = null;
    }
  }

  /**
   * Internal helper:
   * Save the current audio blob + preview URL + source type + file name.
   */
  private setCurrentAudio(
    audioBlob: Blob,
    previewUrl: string,
    inputType: 'recording' | 'file',
    fileName: string
  ): void {
    if (this.recordedAudioUrl) {
      URL.revokeObjectURL(this.recordedAudioUrl);
    }

    this.lastAudioBlob = audioBlob;
    this.recordedAudioUrl = previewUrl;
    this.selectedInputType = inputType;
    this.selectedAudioName = fileName;
  }

  /**
   * Clean up temporary browser object URLs.
   */
  ngOnDestroy(): void {
    if (this.recordedAudioUrl) {
      URL.revokeObjectURL(this.recordedAudioUrl);
    }
  }
}