// frontend/nepali-voice-ui/src/app/app.component.ts
//
// Root Angular component.
//
// Before login:
//   shows LoginComponent
//
// After login:
//   shows VoiceConsoleComponent
//
// Beginner explanation:
// This is frontend hiding/showing.
// Backend is still separately protected by JWT token validation.

import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

import { LoginComponent } from './components/login/login.component';
import { VoiceConsoleComponent } from './components/voice-console/voice-console.component';
import { AuthService } from './services/auth.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    LoginComponent,
    VoiceConsoleComponent
  ],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent {
  title = 'nepali-voice-ui';

  isLoggedIn = false;
  username = '';

  constructor(private authService: AuthService) {
    this.refreshLoginState();
  }

  onLoginSucceeded(): void {
    this.refreshLoginState();
  }

  logout(): void {
    this.authService.logout();
    this.refreshLoginState();
  }

  private refreshLoginState(): void {
    this.isLoggedIn = this.authService.isLoggedIn();
    this.username = this.authService.getUsername();
  }
}