// frontend/nepali-voice-ui/src/app/services/auth.service.ts
//
// Beginner explanation:
// This Angular service handles login/logout state.
//
// It calls FastAPI:
//   POST /auth/login
//
// If login works, FastAPI returns a token.
// We store that token in sessionStorage.
// sessionStorage clears when the browser tab/session closes.
//
// Later, auth.interceptor.ts reads the token and attaches it to backend requests.

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  username: string;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private baseUrl = 'http://localhost:8000';

  private readonly tokenStorageKey = 'nepali_voice_access_token';
  private readonly usernameStorageKey = 'nepali_voice_username';
  private readonly expiresAtStorageKey = 'nepali_voice_token_expires_at';

  constructor(private http: HttpClient) {}

  login(
    username: string,
    password: string
  ): Observable<LoginResponse> {
    const request: LoginRequest = {
      username,
      password
    };

    return this.http
      .post<LoginResponse>(
        `${this.baseUrl}/auth/login`,
        request
      )
      .pipe(
        tap((response: LoginResponse) => {
          this.saveLogin(response);
        })
      );
  }

  logout(): void {
    sessionStorage.removeItem(this.tokenStorageKey);
    sessionStorage.removeItem(this.usernameStorageKey);
    sessionStorage.removeItem(this.expiresAtStorageKey);
  }

  isLoggedIn(): boolean {
    const token = this.getAccessToken();

    if (!token) {
      return false;
    }

    const expiresAtText = sessionStorage.getItem(this.expiresAtStorageKey);

    if (!expiresAtText) {
      return false;
    }

    const expiresAt = Number(expiresAtText);

    if (!Number.isFinite(expiresAt)) {
      return false;
    }

    if (Date.now() >= expiresAt) {
      this.logout();
      return false;
    }

    return true;
  }

  getAccessToken(): string | null {
    return sessionStorage.getItem(this.tokenStorageKey);
  }

  getUsername(): string {
    return sessionStorage.getItem(this.usernameStorageKey) || '';
  }

  private saveLogin(response: LoginResponse): void {
    const expiresAt = Date.now() + response.expires_in_seconds * 1000;

    sessionStorage.setItem(this.tokenStorageKey, response.access_token);
    sessionStorage.setItem(this.usernameStorageKey, response.username);
    sessionStorage.setItem(this.expiresAtStorageKey, String(expiresAt));
  }
}