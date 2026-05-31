// frontend/nepali-voice-ui/src/app/services/voice.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export type TranscriptionProvider = 'auto' | 'local' | 'openai';

export interface MatchedPhrase {
  id: string;
  aliases: string[];
  clip_filename: string;
  minimum_score?: number;
}

export interface PhraseMatchResult {
  matched: boolean;
  matched_phrase: MatchedPhrase | null;
  matched_alias: string | null;
  score: number;
  used_minimum_score: number;
  clip_exists: boolean;
  clip_url: string | null;
}

export interface OutputDecision {
  output_mode: 'replay_clip' | 'no_clip_match';
  output_clip_url: string | null;
  output_phrase_id: string | null;
  output_phrase_alias: string | null;
}

export interface FileInfo {
  original_filename: string;
  saved_filename: string;
  content_type: string | null;
  size_in_bytes: number;
  saved_path: string;
}

export interface TranscriptionAttempt {
  provider: string;
  provider_model_used: string;
  audio_duration_seconds: number | null;
  estimated_cost_usd: number | null;
  transcript: string;
  phrase_match: PhraseMatchResult;
}

export interface DebugAliasScore {
  alias: string;
  score: number;
}

export interface DebugPhraseScore {
  phrase_id: string;
  clip_filename: string;
  best_alias: string | null;
  best_score: number;
  phrase_minimum_score: number;
  passes_phrase_threshold: boolean;
  clip_exists: boolean;
  clip_url: string | null;
  alias_scores: DebugAliasScore[];
}

export interface TranscribeAndMatchResponse {
  message: string;
  transcript: string;
  detected_language: string | null;
  language_probability: number | null;
  language_mode: string;
  provider_requested: string;
  provider_used: string;
  provider_model_used: string;
  fallback_used: boolean;
  fallback_reason: string | null;
  default_match_threshold: number;
  audio_duration_seconds: number | null;
  cost_estimate_usd: number | null;
  phrase_match: PhraseMatchResult;
  output_decision: OutputDecision;
  transcription_attempts: TranscriptionAttempt[];
  debug_scores?: DebugPhraseScore[];
  file_info: FileInfo;
}

@Injectable({
  providedIn: 'root'
})
export class VoiceService {
  private baseUrl = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  /**
   * Send audio to the backend for transcription + phrase matching.
   *
   * IMPORTANT:
   * The backend expects:
   * - "file" for the uploaded audio
   * - "provider" for provider selection
   */
  transcribeAndMatch(
    audioFile: Blob,
    fileName: string,
    provider: TranscriptionProvider
  ): Observable<TranscribeAndMatchResponse> {
    const formData = new FormData();
    formData.append('file', audioFile, fileName);
    formData.append('provider', provider);

    return this.http.post<TranscribeAndMatchResponse>(
      `${this.baseUrl}/transcribe-and-match`,
      formData
    );
  }

  /**
   * Convert a relative backend clip URL into a full browser URL.
   */
  getFullClipUrl(relativeClipUrl: string | null): string | null {
    if (!relativeClipUrl) {
      return null;
    }

    return `${this.baseUrl}${relativeClipUrl}`;
  }
}