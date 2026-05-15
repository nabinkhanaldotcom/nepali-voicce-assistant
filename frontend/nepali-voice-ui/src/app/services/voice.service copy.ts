import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface TranscribeAndMatchResponse {
  text: string;
}

@Injectable({
  providedIn: 'root'
})
export class VoiceService {

  // Just hardcode backend URL for now.
  // You can later move this to a config if you want.
  private baseUrl = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  /**
   * Send recorded audio to TranscribeAndMatch endpoint.
   * Backend should expect form-data field "audio".
   */
  transcribeAndMatch(audioBlob: Blob): Observable<TranscribeAndMatchResponse> {
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.webm');

    return this.http.post<TranscribeAndMatchResponse>(`${this.baseUrl}/transcribe-and-match`, formData);
  }

  /**
   * Send text to TTS endpoint and get an audio Blob back.
   */
  tts(text: string): Observable<Blob> {
    return this.http.post(`${this.baseUrl}/tts`, { text }, {
      responseType: 'blob'  // we expect raw audio bytes
    });
  }
}

