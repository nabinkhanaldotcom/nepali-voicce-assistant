// frontend/nepali-voice-ui/src/app/services/voice.service.ts

// This service is the frontend's "backend caller".
// It sends audio to FastAPI and receives JSON back.

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

// Information about the matched phrase returned by the backend.
export interface MatchedPhrase {
  id: string;
  aliases: string[];
  clip_filename: string;
}

// Information about phrase matching returned by the backend.
export interface PhraseMatchResult {
  matched: boolean;
  matched_phrase: MatchedPhrase | null;
  matched_alias: string | null;
  score: number;
  clip_exists: boolean;
  clip_url: string | null;
}

// Information about the saved uploaded file.
export interface FileInfo {
  original_filename: string;
  saved_filename: string;
  content_type: string | null;
  size_in_bytes: number;
  saved_path: string;
}

// Full backend response from /transcribe-and-match.
export interface TranscribeAndMatchResponse {
  message: string;
  transcript: string;
  detected_language: string;
  language_probability: number;
  language_mode: string;
  phrase_match: PhraseMatchResult;
  file_info: FileInfo;
}

@Injectable({
  providedIn: 'root'
})
export class VoiceService {
  // Backend base URL
  private baseUrl = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  /**
   * Send audio to the backend for transcription + phrase matching.
   *
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
   * Convert a relative clip URL like:
   *   /phrase-clips/example.m4a
   * into a full browser URL like:
   *   http://localhost:8000/phrase-clips/example.m4a
   */
  getFullClipUrl(relativeClipUrl: string | null): string | null {
    if (!relativeClipUrl) {
      return null;
    }

    return `${this.baseUrl}${relativeClipUrl}`;
  }
}