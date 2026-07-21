// frontend/nepali-voice-ui/src/app/app.component.ts
//
// Root Angular component.
//
// Login screen is intentionally hidden for public/demo use.
// Backend login enforcement is controlled separately by AUTH_REQUIRED=false.

import { Component } from '@angular/core';

import { VoiceConsoleComponent } from './components/voice-console/voice-console.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [VoiceConsoleComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent {
  title = 'nepali-voice-ui';
}