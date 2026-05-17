// frontend/nepali-voice-ui/src/app/components/voice-console/voice-console.component.ts

// This component controls the UI page.
// It can:
// 1. record audio from the microphone
// 2. let the user pick an audio file from the computer
// 3. send the audio to the backend
// 4. show transcript + phrase match result
// 5. play the matched phrase clip
// 6. show a custom three-dot menu for preview actions
// 7. stop old playback before new playback starts
// 8. ignore stale repeated recording-start clicks

import { Component, HostListener, NgZone, OnDestroy } from '@angular/core';
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

  // This number helps ignore stale/older recording-start attempts.
  private latestRecordingRequestId = 0;

  // Keep track of current backend request so we can cancel the older one.
  private currentRequestSubscription: Subscription | null = null;

  // Keep track of current matched-clip playback so we can stop it.
  private currentPlaybackAudio: HTMLAudioElement | null = null;

  // The currently selected audio (recorded or chosen file)
  lastAudioBlob: Blob | null = null;
  recordedAudioUrl: string | null = null;

  constructor(
    private voiceService: VoiceService,
    private ngZone: NgZone
  ) {}

  /**
   * Close the preview menu when the user clicks anywhere outside it.
   */
  @HostListener('document:click')
  onDocumentClick(): void {
    this.previewMenuOpen = false;
  }

  /**
   * Start recording audio from the microphone.
   *
   * Behavior:
   * - ignore repeated clicks while we are already recording
   * - ignore repeated clicks while microphone permission is still preparing
   * - stop old matched playback before starting recording
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

    // Stop any currently playing matched clip before recording begins.
    this.stopMatchedClipPlayback();

    this.isPreparingRecording = true;

    // Increase request id so older in-flight start requests can be ignored.
    const requestId = ++this.latestRecordingRequestId;

    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((stream: MediaStream) => {
        // If this response belongs to an older click, ignore it.
        if (requestId !== this.latestRecordingRequestId) {
          stream.getTracks().forEach((track: MediaStreamTrack) => track.stop());
          return;
        }

        this.audioChunks = [];
        this.currentRecordingStream = stream;
        this.mediaRecorder = new MediaRecorder(stream);

        // Save each chunk produced by the recorder.
        this.mediaRecorder.ondataavailable = (event: BlobEvent) => {
          if (event.data && event.data.size > 0) {
            this.audioChunks.push(event.data);
          }
        };

        // When the recorder stops, combine chunks into one Blob.
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
   * Stop the current microphone recording.
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
   * Called when the user chooses an audio file from the file picker.
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

    // Stop matched clip playback before switching source.
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
   * Send the selected audio to the backend.
   *
   * If an older request is still in progress, cancel it and use the latest one.
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

    // Cancel older request if one is still running.
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
   * Play the matched clip.
   *
   * If a previous matched clip is already playing, stop it first.
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
   * Stop the currently playing matched clip, if any.
   */
  private stopMatchedClipPlayback(): void {
    if (this.currentPlaybackAudio) {
      this.currentPlaybackAudio.pause();
      this.currentPlaybackAudio.currentTime = 0;
      this.currentPlaybackAudio = null;
    }
  }

  /**
   * Toggle the custom preview menu.
   *
   * stopPropagation() prevents the document click handler
   * from closing it immediately.
   */
  togglePreviewMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.previewMenuOpen = !this.previewMenuOpen;
  }

  /**
   * Close the preview menu manually.
   */
  closePreviewMenu(): void {
    this.previewMenuOpen = false;
  }

  /**
   * Clear the current selected/recorded audio.
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
   * Helper:
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
    this.previewMenuOpen = false;
  }

  /**
   * Cleanup when the component is destroyed.
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