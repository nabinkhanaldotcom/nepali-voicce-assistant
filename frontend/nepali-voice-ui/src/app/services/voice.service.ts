// frontend/nepali-voice-ui/src/app/services/voice.service.ts
//
// Angular service explanation:
// This file is like a small client for your FastAPI backend.
// Components should not hardcode HTTP request details everywhere.
// The component calls this service, and this service calls FastAPI.

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export type TranscriptionProvider = 'local_whisper' | 'openai_whisper';

export type OpenAiTranscriptionModel =
  | 'gpt-4o-mini-transcribe'
  | 'gpt-4o-transcribe';

export type TonePreset =
  | 'original'
  | 'happy'
  | 'sad'
  | 'punchline';

export type AudioDownloadFormat =
  | 'weba'
  | 'wav'
  | 'mp3'
  | 'm4a';

export type RvcPitchMethod =
  | 'harvest'
  | 'crepe'
  | 'rmvpe'
  | 'pm';

export interface UploadAudioResponse {
  message: string;
  originalFilename: string;
  savedFilename: string;
  contentType: string | null;
  sizeInBytes: number;
  savedPath: string;
}

export interface FileInfo {
  originalFilename: string;
  savedFilename: string;
  contentType: string | null;
  sizeInBytes: number;
  savedPath: string;
}

export interface MatchedClip {
  id: string;
  displayName: string;
  matchedAlias: string;
  clipFileName: string;
  clipExists: boolean;
  clipUrl: string | null;
}

export interface OutputDecision {
  status: 'placeholder';
  message: string;
  tonePreset: TonePreset | string;
  shouldGenerateVoice: boolean;
}

export interface TranscribeAndMatchResponse {
  message: string;
  providerRequested: TranscriptionProvider | string;
  providerUsed: TranscriptionProvider | string;
  modelUsed: string;
  transcript: string;
  detectedLanguage: string | null;
  languageProbability: number | null;
  durationSeconds: number | null;
  estimatedCostUsd: number;
  tonePreset: TonePreset | string;

  // Simple score only.
  // No minimum score.
  // No debug score.
  // No fallback score.
  score: number;

  matchedClip: MatchedClip | null;
  outputDecision: OutputDecision;
  fileInfo: FileInfo;
}

@Injectable({
  providedIn: 'root'
})
export class VoiceService {
  // FastAPI backend base URL.
  // Later, you can move this to Angular environment config.
  private baseUrl = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  /**
   * Upload audio only.
   *
   * Backend endpoint:
   * POST http://localhost:8000/upload-audio
   */
  uploadAudio(
    audioFile: Blob,
    fileName: string
  ): Observable<UploadAudioResponse> {
    const formData = new FormData();

    formData.append('file', audioFile, fileName);

    return this.http.post<UploadAudioResponse>(
      `${this.baseUrl}/upload-audio`,
      formData
    );
  }

  /**
   * Send audio to the backend for transcription only.
   *
   * Backend endpoint:
   * POST http://localhost:8000/transcribe-audio
   */
  transcribeAudio(
    audioFile: Blob,
    fileName: string,
    provider: TranscriptionProvider,
    openAiModel: OpenAiTranscriptionModel,
    tonePreset: TonePreset
  ): Observable<TranscribeAndMatchResponse> {
    const formData = this.buildAudioFormData(
      audioFile,
      fileName,
      provider,
      openAiModel,
      tonePreset
    );

    return this.http.post<TranscribeAndMatchResponse>(
      `${this.baseUrl}/transcribe-audio`,
      formData
    );
  }

  /**
   * Send audio to the backend for transcription + phrase matching.
   *
   * Backend endpoint:
   * POST http://localhost:8000/transcribe-and-match
   *
   * IMPORTANT:
   * The backend expects multipart form-data:
   * - file
   * - provider
   * - openaiModel
   * - tonePreset
   */
  transcribeAndMatch(
    audioFile: Blob,
    fileName: string,
    provider: TranscriptionProvider,
    openAiModel: OpenAiTranscriptionModel,
    tonePreset: TonePreset
  ): Observable<TranscribeAndMatchResponse> {
    const formData = this.buildAudioFormData(
      audioFile,
      fileName,
      provider,
      openAiModel,
      tonePreset
    );

    return this.http.post<TranscribeAndMatchResponse>(
      `${this.baseUrl}/transcribe-and-match`,
      formData
    );
  }

  /**
   * Generate uncle-style voice using your trained local RVC model.
   *
   * Backend endpoint:
   * POST http://localhost:8000/generate-voice
   *
   * Beginner explanation:
   * Angular sends the recorded/uploaded audio to FastAPI.
   * FastAPI saves it, converts it to clean WAV, calls .venv-rvc,
   * runs your .pth + .index model, and returns generated WAV audio.
   */
  generateVoiceWithRvc(
    audioFile: Blob,
    fileName: string,
    pitch: number,
    indexRate: number,
    protect: number,
    method: RvcPitchMethod
  ): Observable<Blob> {
    const formData = new FormData();

    formData.append('file', audioFile, fileName);
    formData.append('pitch', String(pitch));
    formData.append('indexRate', String(indexRate));
    formData.append('protect', String(protect));
    formData.append('method', method);

    return this.http.post(
      `${this.baseUrl}/generate-voice`,
      formData,
      {
        responseType: 'blob'
      }
    );
  }

  /**
   * Convert audio into a selected download format.
   *
   * Backend endpoint:
   * POST http://localhost:8000/convert-audio-download
   *
   * Beginner explanation:
   * The browser may record audio as webm.
   * If the user wants mp3, wav, or m4a, the backend uses ffmpeg
   * to make a real converted file.
   *
   * WEBA is not sent here. WEBA is downloaded directly from Angular
   * because it is the browser/default recording-style format.
   */
  convertAudioForDownload(
    audioFile: Blob,
    fileName: string,
    outputFormat: Exclude<AudioDownloadFormat, 'weba'>
  ): Observable<Blob> {
    const formData = new FormData();

    formData.append('file', audioFile, fileName);
    formData.append('outputFormat', outputFormat);

    return this.http.post(
      `${this.baseUrl}/convert-audio-download`,
      formData,
      {
        responseType: 'blob'
      }
    );
  }

  /**
   * Convert backend relative clip URL into full browser URL.
   *
   * Backend returns:
   * /phrase-clips/abuiiiAbuiii.m4a
   *
   * Browser needs:
   * http://localhost:8000/phrase-clips/abuiiiAbuiii.m4a
   */
  getFullClipUrl(relativeClipUrl: string | null): string | null {
    if (!relativeClipUrl) {
      return null;
    }

    return `${this.baseUrl}${relativeClipUrl}`;
  }

  private buildAudioFormData(
    audioFile: Blob,
    fileName: string,
    provider: TranscriptionProvider,
    openAiModel: OpenAiTranscriptionModel,
    tonePreset: TonePreset
  ): FormData {
    const formData = new FormData();

    formData.append('file', audioFile, fileName);
    formData.append('provider', provider);
    formData.append('openaiModel', openAiModel);
    formData.append('tonePreset', tonePreset);

    return formData;
  }
}