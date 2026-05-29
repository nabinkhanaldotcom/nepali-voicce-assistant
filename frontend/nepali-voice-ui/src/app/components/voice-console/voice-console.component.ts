// frontend/nepali-voice-ui/src/app/components/voice-console/voice-console.component.ts

import { Component, HostListener, NgZone, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import {
  VoiceService,
  TranscribeAndMatchResponse,
  TranscriptionProvider
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
  // Transcription provider selection
  // -----------------------------
  selectedProvider: TranscriptionProvider = 'auto';

  // -----------------------------
  // Provider result info returned by backend
  // -----------------------------
  providerRequested = '';
  providerUsed = '';
  providerModelUsed = '';
  fallbackUsed = false;
  fallbackReason = '';
  audioDurationSeconds: number | null = null;
  costEstimateUsd: number | null = null;

  // -----------------------------
  // Language info returned by backend
  // -----------------------------
  detectedLanguage = '';
  languageProbability: number | null = null;
  languageMode = '';

  // -----------------------------
  // Phrase match info returned by backend
  // -----------------------------
  matchFound = false;
  matchScore: number | null = null;
  matchedPhraseText = '';
  matchedClipUrl: string | null = null;
  matchedClipExists = false;

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

    this.stopMatchedClipPlayback();
    this.isPreparingRecording = true;

    const requestId = ++this.latestRecordingRequestId;

    navigator.mediaDevices.getUserMedia({ audio: true })
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

    this.currentRequestSubscription = this.voiceService
      .transcribeAndMatch(this.lastAudioBlob, this.selectedAudioName, this.selectedProvider)
      .subscribe({
        next: (res: TranscribeAndMatchResponse) => {
          this.recognizedText = res.transcript || '';

          this.providerRequested = res.provider_requested || '';
          this.providerUsed = res.provider_used || '';
          this.providerModelUsed = res.provider_model_used || '';
          this.fallbackUsed = res.fallback_used ?? false;
          this.fallbackReason = res.fallback_reason || '';
          this.audioDurationSeconds = res.audio_duration_seconds ?? null;
          this.costEstimateUsd = res.cost_estimate_usd ?? null;

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
   * Play the matched clip.
   */
  playMatchedClip(): void {
    if (!this.matchedClipUrl) {
      this.errorMessage = 'No matched clip is available.';
      return;
    }

    this.stopMatchedClipPlayback();

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
   * Toggle the preview menu.
   */
  togglePreviewMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.previewMenuOpen = !this.previewMenuOpen;
  }

  /**
   * Close preview menu.
   */
  closePreviewMenu(): void {
    this.previewMenuOpen = false;
  }

  /**
   * Clear current selected/recorded audio.
   */
  clearSelectedAudio(): void {
    this.lastAudioBlob = null;
    this.selectedInputType = null;
    this.selectedAudioName = '';
    this.previewMenuOpen = false;

    if (this.recordedAudioUrl) {
      URL.revokeObjectURL(this.recordedAudioUrl);
      this.recordedAudioUrl = null;
    }
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