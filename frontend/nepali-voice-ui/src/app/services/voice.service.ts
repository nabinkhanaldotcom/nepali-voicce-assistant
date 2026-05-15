import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface MatchedPhrase {
  id: string;
  phrase_text: string;
  clip_filename: string;
}

export interface PhraseMatchResult {
  matched: boolean;
  matched_phrase: MatchedPhrase | null;
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
  private baseUrl = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  transcribeAndMatch(audioFile: Blob, fileName: string): Observable<TranscribeAndMatchResponse> {
    const formData = new FormData();

    // IMPORTANT:
    // your new FastAPI endpoint expects the field name "file"
    // formData.append('file', audioBlob, 'recording.webm');

    formData.append('file', audioFile, fileName);

    return this.http.post<TranscribeAndMatchResponse>(
      `${this.baseUrl}/transcribe-and-match`,
      formData
    );
  }

  getFullClipUrl(relativeClipUrl: string | null): string | null {
    if (!relativeClipUrl) {
      return null;
    }

    return `${this.baseUrl}${relativeClipUrl}`;
  }
}