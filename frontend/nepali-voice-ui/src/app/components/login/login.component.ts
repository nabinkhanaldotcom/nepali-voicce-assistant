// frontend/nepali-voice-ui/src/app/components/login/login.component.ts
//
// Login page component.
//
// Beginner explanation:
// This component shows username/password inputs.
// When login succeeds, it tells AppComponent to show the voice app.

import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  EventEmitter,
  Output
} from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss'
})
export class LoginComponent {
  @Output()
  loginSucceeded = new EventEmitter<void>();

  username = '';
  password = '';

  isLoggingIn = false;
  errorMessage = '';

  constructor(private authService: AuthService) {}

  login(): void {
    this.errorMessage = '';

    const cleanedUsername = this.username.trim();

    if (!cleanedUsername || !this.password) {
      this.errorMessage = 'Bro enter username and password.';
      return;
    }

    this.isLoggingIn = true;

    this.authService
      .login(cleanedUsername, this.password)
      .subscribe({
        next: () => {
          this.isLoggingIn = false;
          this.loginSucceeded.emit();
        },
        error: (err: unknown) => {
          this.isLoggingIn = false;
          this.errorMessage = this.buildErrorMessage(err);
        }
      });
  }

  private buildErrorMessage(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const backendDetail = err.error?.detail;

      if (typeof backendDetail === 'string') {
        return backendDetail;
      }

      return `Login failed with status ${err.status}.`;
    }

    if (err instanceof Error) {
      return err.message;
    }

    return 'Login failed bro. Please try again.';
  }
}