// frontend/nepali-voice-ui/src/app/services/voice.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface MatchedPhrase {
  id: string;
  aliases: string[];
  clip_filename: string;
}

export interface PhraseMatchResult {
  matched: boolean;
  matched_phrase: MatchedPhrase | null;
  matched_alias: string | null;
  score: number;
  clip_exists: boolean;
  clip_url: string | null;
}

export interface FileInfo {
  original_filename: string;
  saved_filename: string;
  content_type: string | null;
  size_in_bytes: number;
  saved_path: string;
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
  clip_exists: boolean;
  clip_url: string | null;
  alias_scores: DebugAliasScore[];
}

export interface TranscribeAndMatchResponse {
  message: string;
  transcript: string;
  detected_language: string;
  language_probability: number;
  language_mode: string;
  match_threshold?: number;
  phrase_match: PhraseMatchResult;
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
   * IMPORTANT:
   * The FastAPI backend expects a form-data field named "file".
   */
  transcribeAndMatch(audioFile: Blob, fileName: string): Observable<TranscribeAndMatchResponse> {
    const formData = new FormData();
    formData.append('file', audioFile, fileName);

    return this.http.post<TranscribeAndMatchResponse>(
      `${this.baseUrl}/transcribe-and-match`,
      formData
    );
  }

  /**
   * Convert a relative backend clip URL such as:
   *   /phrase-clips/example.m4a
   * into a full browser URL.
   */
  getFullClipUrl(relativeClipUrl: string | null): string | null {
    if (!relativeClipUrl) {
      return null;
    }

    return `${this.baseUrl}${relativeClipUrl}`;
  }
}