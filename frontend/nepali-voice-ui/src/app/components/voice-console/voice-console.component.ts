// frontend/nepali-voice-ui/src/app/components/voice-console/voice-console.component.ts

import { Component, NgZone, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

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
  isPreparingRecording = false;
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
  private currentRecordingStream: MediaStream | null = null;

  // This token helps us ignore stale / older recording-start attempts.
  private latestRecordingRequestId = 0;

  // Keep track of current backend request so we can cancel older ones.
  private currentRequestSubscription: Subscription | null = null;

  // Keep track of currently playing matched clip.
  private currentPlaybackAudio: HTMLAudioElement | null = null;

  // The currently selected audio (recorded or chosen file)
  lastAudioBlob: Blob | null = null;
  recordedAudioUrl: string | null = null;

  constructor(
    private voiceService: VoiceService,
    private ngZone: NgZone
  ) {}

  /**
   * Start recording audio from the microphone.
   *
   * Behavior:
   * - if an older "start" request is still in progress, ignore it
   * - if a matched clip is currently playing, stop it first
   */
  startRecording(): void {
    this.errorMessage = '';

    // Ignore repeated starts while we are already recording
    // or while the browser permission request is still in progress.
    if (this.isRecording || this.isPreparingRecording) {
      return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.errorMessage = 'This browser does not support microphone recording.';
      return;
    }

    // Stop any matched clip playback before recording starts.
    this.stopMatchedClipPlayback();

    // Mark that a recording start is in progress.
    this.isPreparingRecording = true;

    // Create a new request ID.
    // If another startRecording() call happens later, older responses can be ignored.
    const requestId = ++this.latestRecordingRequestId;

    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((stream: MediaStream) => {
        // If this is not the latest request anymore, immediately stop it.
        if (requestId !== this.latestRecordingRequestId) {
          stream.getTracks().forEach((track: MediaStreamTrack) => track.stop());
          return;
        }

        this.audioChunks = [];
        this.currentRecordingStream = stream;
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

        this.isPreparingRecording = false;
        this.isRecording = true;
      })
      .catch((err: unknown) => {
        console.error('Microphone access error:', err);
        this.errorMessage = 'Could not access microphone. Please allow microphone permission.';
        this.isPreparingRecording = false;
      });
  }

  /**
   * Stop microphone recording.
   */
  stopRecording(): void {
    if (this.mediaRecorder && this.isRecording) {
      this.mediaRecorder.stop();

      if (this.currentRecordingStream) {
        this.currentRecordingStream.getTracks().forEach((track: MediaStreamTrack) => track.stop());
        this.currentRecordingStream = null;
      }

      this.isRecording = false;
      this.isPreparingRecording = false;
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

    if (!selectedFile.type.startsWith('audio/')) {
      this.errorMessage = 'Please choose a valid audio file.';
      return;
    }

    // Stop any matched clip playback before switching input.
    this.stopMatchedClipPlayback();

    const previewUrl = URL.createObjectURL(selectedFile);

    this.setCurrentAudio(
      selectedFile,
      previewUrl,
      'file',
      selectedFile.name
    );
  }

  /**
   * Send the current audio to the backend.
   *
   * If an older request is still running, unsubscribe from it
   * and use the newest request instead.
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

    // Cancel older request if it is still active.
    if (this.currentRequestSubscription) {
      this.currentRequestSubscription.unsubscribe();
      this.currentRequestSubscription = null;
    }

    this.isProcessing = true;

    this.currentRequestSubscription = this.voiceService
      .transcribeAndMatch(this.lastAudioBlob, this.selectedAudioName)
      .subscribe({
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
          this.currentRequestSubscription = null;
        },
        error: (err: unknown) => {
          console.error('Backend error:', err);
          this.errorMessage = 'Error sending audio to the backend.';
          this.isProcessing = false;
          this.currentRequestSubscription = null;
        }
      });
  }

  /**
   * Play the matched backend clip.
   *
   * If an older clip is still playing, stop it first.
   */
  playMatchedClip(): void {
    if (!this.matchedClipUrl) {
      this.errorMessage = 'No matched clip is available.';
      return;
    }

    // Stop the currently playing clip before starting a new one.
    this.stopMatchedClipPlayback();

    const audio = new Audio(this.matchedClipUrl);
    this.currentPlaybackAudio = audio;

    // When playback ends, clear the reference.
    audio.onended = () => {
      if (this.currentPlaybackAudio === audio) {
        this.currentPlaybackAudio = null;
      }
    };

    audio.play().catch((err: unknown) => {
      console.warn('Audio play error:', err);
      this.errorMessage = 'Could not play the matched clip.';
    });
  }

  /**
   * Stop any currently playing matched clip.
   */
  private stopMatchedClipPlayback(): void {
    if (this.currentPlaybackAudio) {
      this.currentPlaybackAudio.pause();
      this.currentPlaybackAudio.currentTime = 0;
      this.currentPlaybackAudio = null;
    }
  }

  /**
   * Clear the selected/recorded audio from the UI.
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
   * Helper:
   * Save the current audio blob + preview URL + input type + file name.
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
   * Cleanup when component is destroyed.
   */
  ngOnDestroy(): void {
    if (this.currentRequestSubscription) {
      this.currentRequestSubscription.unsubscribe();
      this.currentRequestSubscription = null;
    }

    this.stopMatchedClipPlayback();

    if (this.currentRecordingStream) {
      this.currentRecordingStream.getTracks().forEach((track: MediaStreamTrack) => track.stop());
      this.currentRecordingStream = null;
    }

    if (this.recordedAudioUrl) {
      URL.revokeObjectURL(this.recordedAudioUrl);
    }
  }
}