// frontend/nepali-voice-ui/src/app/components/voice-console/voice-console.component.ts
//
// This component controls the browser UI:
// - record audio
// - stop recording automatically after 60 seconds
// - upload audio
// - custom audio preview player
// - select provider
// - select OpenAI model if needed
// - select tone preset
// - select download format
// - send audio to FastAPI
// - show transcript and matched clip
// - play matched clip
// - generate Artist's Voice using local RVC
// - download preview/matched/generated audio

import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  ElementRef,
  HostListener,
  NgZone,
  OnDestroy,
  ViewChild
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import {
  AudioDownloadFormat,
  MatchedClip,
  OpenAiTranscriptionModel,
  RvcPitchMethod,
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
  @ViewChild('previewAudioElement')
  previewAudioElement?: ElementRef<HTMLAudioElement>;

  // -----------------------------
  // Recording limits
  // -----------------------------
  readonly maxRecordingSeconds = 10;

  recordingElapsedSeconds = 0;
  recordingRemainingSeconds = this.maxRecordingSeconds;

  private recordingLimitTimeoutId: number | null = null;
  private recordingTimerIntervalId: number | null = null;

  // -----------------------------
  // Frontend file allowlist
  // -----------------------------
  readonly allowedAudioExtensions = [
    '.wav',
    '.mp3',
    '.m4a',
    '.weba',
    '.webm',
    '.ogg',
    '.mpeg',
    '.mpga',
    '.flac'
  ];

  // -----------------------------
  // UI states
  // -----------------------------
  isRecording = false;
  isPreparingRecording = false;
  isProcessing = false;
  isDownloadingAudio = false;
  isGeneratingVoice = false;

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
  // RVC voice generation settings
  // -----------------------------
  // These defaults match the settings that worked from PowerShell.
  rvcPitch = 12;
  rvcIndexRate = 0.75;
  rvcProtect = 0.5;
  rvcMethod: RvcPitchMethod = 'rmvpe';

  // -----------------------------
  // Download format selection
  // -----------------------------
  selectedDownloadFormat: AudioDownloadFormat = 'weba';

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
  // Future output-generation placeholder returned by transcription endpoint
  // -----------------------------
  outputDecisionStatus = '';
  outputDecisionMessage = '';
  outputDecisionTonePreset = '';
  outputDecisionShouldGenerateVoice = false;

  // -----------------------------
  // Generated RVC voice result
  // -----------------------------
  generatedVoiceBlob: Blob | null = null;
  generatedVoiceUrl: string | null = null;
  generatedVoiceFileName = '';

  // -----------------------------
  // Audio source info
  // -----------------------------
  selectedInputType: 'recording' | 'file' | null = null;
  selectedAudioName = '';

  // -----------------------------
  // Custom audio preview player state
  // -----------------------------
  previewMenuOpen = false;
  isPreviewPlaying = false;
  previewCurrentTime = 0;
  previewDuration = 0;
  previewPlaybackSpeed = 1;

  readonly playbackSpeedOptions = [0.5, 0.75, 1, 1.25, 1.5, 2];

  // -----------------------------
  // MediaRecorder-related state
  // -----------------------------
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private currentRecordingStream: MediaStream | null = null;
  private latestRecordingRequestId = 0;
  private currentRecordingMimeType = '';

  private readonly preferredRecordingMimeTypes = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/ogg',
    'audio/mp4'
  ];

  // -----------------------------
  // Request / playback management
  // -----------------------------
  private currentRequestSubscription: Subscription | null = null;
  private currentGenerateSubscription: Subscription | null = null;
  private currentDownloadSubscription: Subscription | null = null;
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

  get generatedVoiceDownloadFormatLabel(): string {
    if (this.selectedDownloadFormat === 'weba') {
      return 'WAV';
    }

    return this.selectedDownloadFormat.toUpperCase();
  }

  @HostListener('document:click')
  onDocumentClick(): void {
    this.previewMenuOpen = false;
  }

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
    this.stopPreviewPlayback();
    this.clearResultsOnly();
    this.clearGeneratedVoiceOnly();

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

        const supportedMimeType = this.getBestSupportedRecordingMimeType();
        this.currentRecordingMimeType = supportedMimeType;

        const recorderOptions = supportedMimeType
          ? { mimeType: supportedMimeType }
          : undefined;

        this.mediaRecorder = new MediaRecorder(stream, recorderOptions);

        this.mediaRecorder.ondataavailable = (event: BlobEvent) => {
          if (event.data && event.data.size > 0) {
            this.audioChunks.push(event.data);
          }
        };

        this.mediaRecorder.onstop = () => {
          const recorderMimeType =
            this.currentRecordingMimeType ||
            this.mediaRecorder?.mimeType ||
            'audio/webm';

          const audioBlob = new Blob(this.audioChunks, {
            type: recorderMimeType
          });

          const extension = this.getFileExtensionForMimeType(recorderMimeType);

          this.ngZone.run(() => {
            this.setCurrentAudio(
              audioBlob,
              URL.createObjectURL(audioBlob),
              'recording',
              `recording.${extension}`
            );
          });
        };

        this.mediaRecorder.start();

        this.isPreparingRecording = false;
        this.isRecording = true;

        this.startRecordingLimitTimer();
      })
      .catch((err: unknown) => {
        console.error('Microphone access error:', err);

        this.errorMessage = 'Could not access microphone. Please allow microphone permission.';
        this.isPreparingRecording = false;
        this.clearRecordingLimitTimer();
      });
  }

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
      this.clearRecordingLimitTimer();
    }
  }

  onFileSelected(event: Event): void {
    this.errorMessage = '';

    const input = event.target as HTMLInputElement;

    if (!input.files || input.files.length === 0) {
      return;
    }

    if (input.files.length !== 1) {
      this.errorMessage = 'Please choose only one audio file.';
      input.value = '';
      return;
    }

    const selectedFile = input.files[0];

    if (!this.isAllowedAudioFile(selectedFile)) {
      this.errorMessage =
        'Please choose a valid audio file. Allowed types: WAV, MP3, M4A, WEBA, WEBM, OGG, MPEG, MPGA, FLAC.';
      input.value = '';
      return;
    }

    this.stopCurrentAudioPlayback();
    this.stopPreviewPlayback();
    this.clearResultsOnly();
    this.clearGeneratedVoiceOnly();

    const previewUrl = URL.createObjectURL(selectedFile);

    this.setCurrentAudio(
      selectedFile,
      previewUrl,
      'file',
      selectedFile.name
    );
  }

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

          this.errorMessage = this.buildBackendErrorMessage(err);

          this.isProcessing = false;
          this.currentRequestSubscription = null;
        }
      });
  }

  generateArtistVoice(): void {
    this.errorMessage = '';

    if (!this.lastAudioBlob) {
      this.errorMessage = 'No audio available. Please record or choose a file first.';
      return;
    }

    if (!this.selectedAudioName) {
      this.errorMessage = 'Audio file name is missing.';
      return;
    }

    if (this.currentGenerateSubscription) {
      this.currentGenerateSubscription.unsubscribe();
      this.currentGenerateSubscription = null;
    }

    this.clearGeneratedVoiceOnly();
    this.isGeneratingVoice = true;

    this.currentGenerateSubscription = this.voiceService
      .generateVoiceWithRvc(
        this.lastAudioBlob,
        this.selectedAudioName,
        this.rvcPitch,
        this.rvcIndexRate,
        this.rvcProtect,
        this.rvcMethod
      )
      .subscribe({
        next: (generatedBlob: Blob) => {
          this.generatedVoiceBlob = generatedBlob;
          this.generatedVoiceFileName = 'generated-artists-voice.wav';
          this.generatedVoiceUrl = URL.createObjectURL(generatedBlob);

          this.isGeneratingVoice = false;
          this.currentGenerateSubscription = null;
        },
        error: (err: unknown) => {
          console.error('RVC voice generation error:', err);

          this.errorMessage = this.buildBackendErrorMessage(err);

          this.isGeneratingVoice = false;
          this.currentGenerateSubscription = null;
        }
      });
  }

  onPreviewLoaded(): void {
    const audio = this.previewAudioElement?.nativeElement;

    if (!audio) {
      return;
    }

    this.previewDuration = Number.isFinite(audio.duration) ? audio.duration : 0;
    audio.playbackRate = this.previewPlaybackSpeed;
  }

  onPreviewTimeUpdate(): void {
    const audio = this.previewAudioElement?.nativeElement;

    if (!audio) {
      return;
    }

    this.previewCurrentTime = audio.currentTime || 0;
    this.previewDuration = Number.isFinite(audio.duration) ? audio.duration : 0;
  }

  onPreviewEnded(): void {
    this.isPreviewPlaying = false;

    const audio = this.previewAudioElement?.nativeElement;

    if (audio) {
      audio.currentTime = 0;
    }

    this.previewCurrentTime = 0;
  }

  togglePreviewPlayback(): void {
    const audio = this.previewAudioElement?.nativeElement;

    if (!audio) {
      return;
    }

    this.stopCurrentAudioPlayback();

    if (this.isPreviewPlaying) {
      audio.pause();
      this.isPreviewPlaying = false;
      return;
    }

    audio.playbackRate = this.previewPlaybackSpeed;

    audio
      .play()
      .then(() => {
        this.isPreviewPlaying = true;
      })
      .catch((err: unknown) => {
        console.warn('Preview audio play error:', err);
        this.errorMessage = 'Could not play the preview audio.';
      });
  }

  seekPreviewAudio(event: Event): void {
    const audio = this.previewAudioElement?.nativeElement;
    const input = event.target as HTMLInputElement;

    if (!audio) {
      return;
    }

    const nextTime = Number(input.value);

    if (!Number.isFinite(nextTime)) {
      return;
    }

    audio.currentTime = nextTime;
    this.previewCurrentTime = nextTime;
  }

  setPreviewPlaybackSpeed(speed: number): void {
    this.previewPlaybackSpeed = speed;

    const audio = this.previewAudioElement?.nativeElement;

    if (audio) {
      audio.playbackRate = speed;
    }
  }

  formatAudioTime(seconds: number): string {
    if (!Number.isFinite(seconds) || seconds < 0) {
      return '0:00';
    }

    const totalSeconds = Math.floor(seconds);
    const minutes = Math.floor(totalSeconds / 60);
    const remainingSeconds = totalSeconds % 60;

    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }

  downloadPreviewAudio(): void {
    this.errorMessage = '';
    this.previewMenuOpen = false;

    if (!this.lastAudioBlob) {
      this.errorMessage = 'No audio is available to download.';
      return;
    }

    const fileName = this.selectedAudioName || 'preview-audio.webm';

    this.convertAndDownloadAudioBlob(
      this.lastAudioBlob,
      fileName,
      'preview-audio'
    );
  }

  downloadMatchedClip(): void {
    this.errorMessage = '';

    if (!this.matchedClipUrl || !this.matchedClip) {
      this.errorMessage = 'No matched clip is available to download.';
      return;
    }

    this.isDownloadingAudio = true;

    fetch(this.matchedClipUrl)
      .then((response: Response) => {
        if (!response.ok) {
          throw new Error(`Could not download matched clip. HTTP status: ${response.status}`);
        }

        return response.blob();
      })
      .then((clipBlob: Blob) => {
        this.ngZone.run(() => {
          this.convertAndDownloadAudioBlob(
            clipBlob,
            this.matchedClip?.clipFileName || 'matched-clip.m4a',
            'matched-clip'
          );
        });
      })
      .catch((err: unknown) => {
        console.error('Matched clip download error:', err);

        this.ngZone.run(() => {
          this.errorMessage =
            err instanceof Error
              ? err.message
              : 'Could not download matched clip.';

          this.isDownloadingAudio = false;
        });
      });
  }

  downloadGeneratedVoice(): void {
    this.errorMessage = '';

    if (!this.generatedVoiceBlob) {
      this.errorMessage = 'No generated voice is available to download.';
      return;
    }

    if (this.selectedDownloadFormat === 'weba') {
      this.downloadBlobDirectly(
        this.generatedVoiceBlob,
        this.generatedVoiceFileName || 'generated-artists-voice.wav'
      );

      return;
    }

    this.convertAndDownloadAudioBlob(
      this.generatedVoiceBlob,
      this.generatedVoiceFileName || 'generated-artists-voice.wav',
      'generated-artists-voice'
    );
  }

  private convertAndDownloadAudioBlob(
    audioBlob: Blob,
    sourceFileName: string,
    fallbackBaseName: string
  ): void {
    if (this.currentDownloadSubscription) {
      this.currentDownloadSubscription.unsubscribe();
      this.currentDownloadSubscription = null;
    }

    if (this.selectedDownloadFormat === 'weba') {
      this.downloadBlobDirectly(
        audioBlob,
        `${this.getBaseFileName(sourceFileName, fallbackBaseName)}.weba`
      );

      this.isDownloadingAudio = false;
      return;
    }

    this.isDownloadingAudio = true;

    this.currentDownloadSubscription = this.voiceService
      .convertAudioForDownload(
        audioBlob,
        sourceFileName,
        this.selectedDownloadFormat
      )
      .subscribe({
        next: (convertedBlob: Blob) => {
          const downloadFileName =
            `${this.getBaseFileName(sourceFileName, fallbackBaseName)}.${this.selectedDownloadFormat}`;

          this.downloadBlobDirectly(convertedBlob, downloadFileName);

          this.isDownloadingAudio = false;
          this.currentDownloadSubscription = null;
        },
        error: (err: unknown) => {
          console.error('Audio conversion/download error:', err);

          this.errorMessage = this.buildBackendErrorMessage(err);

          this.isDownloadingAudio = false;
          this.currentDownloadSubscription = null;
        }
      });
  }

  private downloadBlobDirectly(
    audioBlob: Blob,
    downloadFileName: string
  ): void {
    const downloadUrl = URL.createObjectURL(audioBlob);
    const link = document.createElement('a');

    link.href = downloadUrl;
    link.download = downloadFileName;

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(downloadUrl);
  }

  private getBaseFileName(fileName: string, fallbackBaseName: string): string {
    const cleanedFileName = (fileName || '').trim();

    if (!cleanedFileName) {
      return fallbackBaseName;
    }

    const lastDotIndex = cleanedFileName.lastIndexOf('.');

    if (lastDotIndex <= 0) {
      return cleanedFileName || fallbackBaseName;
    }

    return cleanedFileName.substring(0, lastDotIndex) || fallbackBaseName;
  }

  private buildBackendErrorMessage(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const backendDetail = err.error?.detail;

      if (typeof backendDetail === 'string') {
        return backendDetail;
      }

      if (Array.isArray(backendDetail)) {
        return backendDetail
          .map((item: unknown) => JSON.stringify(item))
          .join(' | ');
      }

      if (err.error instanceof Blob) {
        return `Backend request failed with status ${err.status}. Check FastAPI terminal logs.`;
      }

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

  playMatchedClip(): void {
    if (!this.matchedClipUrl) {
      this.errorMessage = 'No matched clip is available.';
      return;
    }

    this.stopPreviewPlayback();
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

  private stopCurrentAudioPlayback(): void {
    if (this.currentPlaybackAudio) {
      this.currentPlaybackAudio.pause();
      this.currentPlaybackAudio.currentTime = 0;
      this.currentPlaybackAudio = null;
    }
  }

  private stopPreviewPlayback(): void {
    const audio = this.previewAudioElement?.nativeElement;

    if (audio) {
      audio.pause();
    }

    this.isPreviewPlaying = false;
  }

  togglePreviewMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.previewMenuOpen = !this.previewMenuOpen;
  }

  clearSelectedAudio(): void {
    this.stopCurrentAudioPlayback();
    this.stopPreviewPlayback();

    this.lastAudioBlob = null;
    this.selectedInputType = null;
    this.selectedAudioName = '';
    this.previewMenuOpen = false;

    this.previewCurrentTime = 0;
    this.previewDuration = 0;
    this.isPreviewPlaying = false;

    if (this.recordedAudioUrl) {
      URL.revokeObjectURL(this.recordedAudioUrl);
      this.recordedAudioUrl = null;
    }

    this.clearResultsOnly();
    this.clearGeneratedVoiceOnly();
    this.clearRecordingLimitTimer();
  }

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

    this.previewCurrentTime = 0;
    this.previewDuration = 0;
    this.isPreviewPlaying = false;
  }

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

  private clearGeneratedVoiceOnly(): void {
    this.generatedVoiceBlob = null;
    this.generatedVoiceFileName = '';

    if (this.generatedVoiceUrl) {
      URL.revokeObjectURL(this.generatedVoiceUrl);
      this.generatedVoiceUrl = null;
    }
  }

  private startRecordingLimitTimer(): void {
    this.clearRecordingLimitTimer();

    this.recordingElapsedSeconds = 0;
    this.recordingRemainingSeconds = this.maxRecordingSeconds;

    this.recordingTimerIntervalId = window.setInterval(() => {
      this.recordingElapsedSeconds += 1;
      this.recordingRemainingSeconds = Math.max(
        this.maxRecordingSeconds - this.recordingElapsedSeconds,
        0
      );
    }, 1000);

    this.recordingLimitTimeoutId = window.setTimeout(() => {
      if (this.isRecording) {
        this.stopRecording();
      }
    }, this.maxRecordingSeconds * 1000);
  }

  private clearRecordingLimitTimer(): void {
    if (this.recordingLimitTimeoutId !== null) {
      window.clearTimeout(this.recordingLimitTimeoutId);
      this.recordingLimitTimeoutId = null;
    }

    if (this.recordingTimerIntervalId !== null) {
      window.clearInterval(this.recordingTimerIntervalId);
      this.recordingTimerIntervalId = null;
    }

    this.recordingElapsedSeconds = 0;
    this.recordingRemainingSeconds = this.maxRecordingSeconds;
  }

  private getBestSupportedRecordingMimeType(): string {
    if (
      typeof MediaRecorder === 'undefined' ||
      typeof MediaRecorder.isTypeSupported !== 'function'
    ) {
      return '';
    }

    return this.preferredRecordingMimeTypes.find((mimeType: string) =>
      MediaRecorder.isTypeSupported(mimeType)
    ) || '';
  }

  private getFileExtensionForMimeType(mimeType: string): string {
    const normalizedMimeType = (mimeType || '').toLowerCase();

    if (normalizedMimeType.includes('mp4')) {
      return 'm4a';
    }

    if (normalizedMimeType.includes('ogg')) {
      return 'ogg';
    }

    if (normalizedMimeType.includes('mpeg') || normalizedMimeType.includes('mp3')) {
      return 'mp3';
    }

    return 'webm';
  }

  private isAllowedAudioFile(file: File): boolean {
    const extension = this.getLowercaseExtension(file.name);
    const isAllowedExtension = this.allowedAudioExtensions.includes(extension);
    const isAudioMimeType = file.type.toLowerCase().startsWith('audio/');

    return isAllowedExtension || isAudioMimeType;
  }

  private getLowercaseExtension(fileName: string): string {
    const lastDotIndex = fileName.lastIndexOf('.');

    if (lastDotIndex < 0) {
      return '';
    }

    return fileName.substring(lastDotIndex).toLowerCase();
  }

  ngOnDestroy(): void {
    if (this.currentRequestSubscription) {
      this.currentRequestSubscription.unsubscribe();
      this.currentRequestSubscription = null;
    }

    if (this.currentGenerateSubscription) {
      this.currentGenerateSubscription.unsubscribe();
      this.currentGenerateSubscription = null;
    }

    if (this.currentDownloadSubscription) {
      this.currentDownloadSubscription.unsubscribe();
      this.currentDownloadSubscription = null;
    }

    this.stopCurrentAudioPlayback();
    this.stopPreviewPlayback();
    this.clearRecordingLimitTimer();

    if (this.currentRecordingStream) {
      this.currentRecordingStream
        .getTracks()
        .forEach((track: MediaStreamTrack) => track.stop());

      this.currentRecordingStream = null;
    }

    if (this.recordedAudioUrl) {
      URL.revokeObjectURL(this.recordedAudioUrl);
    }

    this.clearGeneratedVoiceOnly();
  }
}