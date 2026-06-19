// frontend/nepali-voice-ui/src/app/components/voice-console/voice-console.component.ts
//
// This component controls the browser UI:
// - record audio
// - upload audio
// - select provider
// - select OpenAI model if needed
// - select tone preset
// - send audio to FastAPI
// - show transcript and matched clip
// - play matched clip

import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, HostListener, NgZone, OnDestroy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import {
  MatchedClip,
  OpenAiTranscriptionModel,
  TonePreset,
  TranscribeAndMatchResponse,
  TranscriptionProvider,
  VoiceService
} from '../../services/voice.service';

@Component({
  selector: 'app-voice-console',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './voice-console.component.html',
  styleUrl: './voice-console.component.scss'
})
export class VoiceConsoleComponent implements OnDestroy {
  // -----------------------------
  // UI states
  // -----------------------------
  isRecording = false;
  isPreparingRecording = false;
  isProcessing = false;

  // -----------------------------
  // Text / error output
  // -----------------------------
  recognizedText = '';
  errorMessage = '';

  // -----------------------------
  // Manual transcription provider selection
  // -----------------------------
  selectedProvider: TranscriptionProvider = 'local_whisper';

  selectedOpenAiModel: OpenAiTranscriptionModel = 'gpt-4o-mini-transcribe';

  selectedTonePreset: TonePreset = 'original';

  // -----------------------------
  // Provider result info returned by backend
  // -----------------------------
  providerRequested = '';
  providerUsed = '';
  modelUsed = '';

  durationSeconds: number | null = null;
  estimatedCostUsd = 0;

  tonePresetReturned = '';

  // -----------------------------
  // Language info returned by backend
  // -----------------------------
  detectedLanguage = '';
  languageProbability: number | null = null;

  // -----------------------------
  // Phrase match info returned by backend
  // -----------------------------
  matchScore: number | null = null;
  matchedClip: MatchedClip | null = null;
  matchedClipUrl: string | null = null;

  // -----------------------------
  // Future output-generation placeholder
  // -----------------------------
  outputDecisionStatus = '';
  outputDecisionMessage = '';
  outputDecisionTonePreset = '';
  outputDecisionShouldGenerateVoice = false;

  // -----------------------------
  // Audio source info
  // -----------------------------
  selectedInputType: 'recording' | 'file' | null = null;
  selectedAudioName = '';

  // -----------------------------
  // Audio preview menu state
  // -----------------------------
  previewMenuOpen = false;

  // -----------------------------
  // MediaRecorder-related state
  // -----------------------------
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private currentRecordingStream: MediaStream | null = null;
  private latestRecordingRequestId = 0;

  // -----------------------------
  // Request / playback management
  // -----------------------------
  private currentRequestSubscription: Subscription | null = null;
  private currentPlaybackAudio: HTMLAudioElement | null = null;

  // -----------------------------
  // Current selected audio
  // -----------------------------
  lastAudioBlob: Blob | null = null;
  recordedAudioUrl: string | null = null;

  constructor(
    private voiceService: VoiceService,
    private ngZone: NgZone
  ) {}

  /**
   * Close the preview menu when user clicks elsewhere.
   */
  @HostListener('document:click')
  onDocumentClick(): void {
    this.previewMenuOpen = false;
  }

  /**
   * Start microphone recording.
   */
  startRecording(): void {
    this.errorMessage = '';

    if (this.isRecording || this.isPreparingRecording) {
      return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.errorMessage = 'This browser does not support microphone recording.';
      return;
    }

    this.stopCurrentAudioPlayback();
    this.clearResultsOnly();

    this.isPreparingRecording = true;
    const requestId = ++this.latestRecordingRequestId;

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream: MediaStream) => {
        if (requestId !== this.latestRecordingRequestId) {
          stream.getTracks().forEach((track: MediaStreamTrack) => track.stop());
          return;
        }

        this.audioChunks = [];
        this.currentRecordingStream = stream;
        this.mediaRecorder = new MediaRecorder(stream);

        this.mediaRecorder.ondataavailable = (event: BlobEvent) => {
          if (event.data && event.data.size > 0) {
            this.audioChunks.push(event.data);
          }
        };

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

        this.errorMessage =
          'Could not access microphone. Please allow microphone permission.';

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
        this.currentRecordingStream
          .getTracks()
          .forEach((track: MediaStreamTrack) => track.stop());

        this.currentRecordingStream = null;
      }

      this.isRecording = false;
      this.isPreparingRecording = false;
    }
  }

  /**
   * Handle file picker selection.
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

    this.stopCurrentAudioPlayback();
    this.clearResultsOnly();

    const previewUrl = URL.createObjectURL(selectedFile);

    this.setCurrentAudio(
      selectedFile,
      previewUrl,
      'file',
      selectedFile.name
    );
  }

  /**
   * Send the current audio to FastAPI.
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

    if (this.currentRequestSubscription) {
      this.currentRequestSubscription.unsubscribe();
      this.currentRequestSubscription = null;
    }

    this.isProcessing = true;
    this.clearResultsOnly();

    this.currentRequestSubscription = this.voiceService
      .transcribeAndMatch(
        this.lastAudioBlob,
        this.selectedAudioName,
        this.selectedProvider,
        this.selectedOpenAiModel,
        this.selectedTonePreset
      )
      .subscribe({
        next: (res: TranscribeAndMatchResponse) => {
          this.applyBackendResponse(res);

          this.isProcessing = false;
          this.currentRequestSubscription = null;
        },
        error: (err: unknown) => {
          console.error('Backend error:', err);

          // Before this change, Angular always showed a generic message.
          // Now we try to show the real FastAPI error detail if the backend sent one.
          //
          // Example FastAPI error response:
          // {
          //   "detail": "OPENAI_API_KEY is not set on the backend server."
          // }
          this.errorMessage = this.buildBackendErrorMessage(err);

          this.isProcessing = false;
          this.currentRequestSubscription = null;
        }
      });
  }

  /**
   * Build a useful error message from Angular/HTTP/backend errors.
   *
   * Beginner explanation:
   * When FastAPI throws HTTPException, the browser usually receives a response like:
   *
   * {
   *   "detail": "Some useful backend error message"
   * }
   *
   * Angular wraps that response inside HttpErrorResponse.
   * This helper method extracts the useful backend message and shows it in the UI.
   */
  private buildBackendErrorMessage(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const backendDetail = err.error?.detail;

      if (typeof backendDetail === 'string') {
        return backendDetail;
      }

      // FastAPI validation errors can sometimes return detail as an array.
      // Example: missing field, invalid form field, wrong type, etc.
      if (Array.isArray(backendDetail)) {
        return backendDetail
          .map((item: unknown) => JSON.stringify(item))
          .join(' | ');
      }

      // Sometimes the backend may return plain text instead of JSON.
      if (typeof err.error === 'string') {
        return err.error;
      }

      return `Backend request failed with status ${err.status}. Check FastAPI terminal logs.`;
    }

    if (err instanceof Error) {
      return err.message;
    }

    return 'Error sending audio to the backend. Check FastAPI terminal logs.';
  }

  /**
   * Copy backend response fields into component fields.
   */
  private applyBackendResponse(res: TranscribeAndMatchResponse): void {
    this.recognizedText = res.transcript || '';

    this.providerRequested = res.providerRequested || '';
    this.providerUsed = res.providerUsed || '';
    this.modelUsed = res.modelUsed || '';

    this.durationSeconds = res.durationSeconds ?? null;
    this.estimatedCostUsd = res.estimatedCostUsd ?? 0;

    this.tonePresetReturned = res.tonePreset || '';

    this.detectedLanguage = res.detectedLanguage || '';
    this.languageProbability = res.languageProbability ?? null;

    this.matchScore = res.score ?? null;

    this.matchedClip = res.matchedClip ?? null;

    this.matchedClipUrl = this.voiceService.getFullClipUrl(
      res.matchedClip?.clipUrl ?? null
    );

    this.outputDecisionStatus = res.outputDecision?.status || '';
    this.outputDecisionMessage = res.outputDecision?.message || '';
    this.outputDecisionTonePreset = res.outputDecision?.tonePreset || '';
    this.outputDecisionShouldGenerateVoice =
      res.outputDecision?.shouldGenerateVoice ?? false;
  }

  /**
   * Play the matched saved phrase clip.
   */
  playMatchedClip(): void {
    if (!this.matchedClipUrl) {
      this.errorMessage = 'No matched clip is available.';
      return;
    }

    this.stopCurrentAudioPlayback();

    const audio = new Audio(this.matchedClipUrl);
    this.currentPlaybackAudio = audio;

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
   * Stop any currently playing audio clip.
   */
  private stopCurrentAudioPlayback(): void {
    if (this.currentPlaybackAudio) {
      this.currentPlaybackAudio.pause();
      this.currentPlaybackAudio.currentTime = 0;
      this.currentPlaybackAudio = null;
    }
  }

  /**
   * Toggle the preview menu near the native audio player.
   */
  togglePreviewMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.previewMenuOpen = !this.previewMenuOpen;
  }

  /**
   * Clear current selected/recorded audio.
   */
  clearSelectedAudio(): void {
    this.stopCurrentAudioPlayback();

    this.lastAudioBlob = null;
    this.selectedInputType = null;
    this.selectedAudioName = '';
    this.previewMenuOpen = false;

    if (this.recordedAudioUrl) {
      URL.revokeObjectURL(this.recordedAudioUrl);
      this.recordedAudioUrl = null;
    }

    this.clearResultsOnly();
  }

  /**
   * Save the current audio blob and preview URL.
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
    this.previewMenuOpen = false;
  }

  /**
   * Clear result values without clearing selected audio.
   */
  private clearResultsOnly(): void {
    this.recognizedText = '';

    this.providerRequested = '';
    this.providerUsed = '';
    this.modelUsed = '';

    this.durationSeconds = null;
    this.estimatedCostUsd = 0;
    this.tonePresetReturned = '';

    this.detectedLanguage = '';
    this.languageProbability = null;

    this.matchScore = null;
    this.matchedClip = null;
    this.matchedClipUrl = null;

    this.outputDecisionStatus = '';
    this.outputDecisionMessage = '';
    this.outputDecisionTonePreset = '';
    this.outputDecisionShouldGenerateVoice = false;
  }

  /**
   * Cleanup when component is destroyed.
   */
  ngOnDestroy(): void {
    if (this.currentRequestSubscription) {
      this.currentRequestSubscription.unsubscribe();
      this.currentRequestSubscription = null;
    }

    this.stopCurrentAudioPlayback();

    if (this.currentRecordingStream) {
      this.currentRecordingStream
        .getTracks()
        .forEach((track: MediaStreamTrack) => track.stop());

      this.currentRecordingStream = null;
    }

    if (this.recordedAudioUrl) {
      URL.revokeObjectURL(this.recordedAudioUrl);
    }
  }
}