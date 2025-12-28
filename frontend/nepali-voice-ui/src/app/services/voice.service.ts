import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface SttResponse {
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
   * Send recorded audio to STT endpoint.
   * Backend should expect form-data field "audio".
   */
  stt(audioBlob: Blob): Observable<SttResponse> {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');

    return this.http.post<SttResponse>(`${this.baseUrl}/stt`, formData);
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

