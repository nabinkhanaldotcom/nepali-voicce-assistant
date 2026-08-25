// frontend/nepali-voice-ui/src/app/app.component.ts
//
// Root Angular component.
//
// Login screen is intentionally hidden for public/demo use.
// Backend login enforcement is controlled separately by AUTH_REQUIRED=false.
//
// This component also controls the portfolio-style mobile navigation menu.

import { Component, signal } from '@angular/core';

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

  // Controls whether the navigation menu is open on smaller screens.
  protected readonly menuOpen = signal(false);

  protected toggleMenu(): void {
    this.menuOpen.update((isOpen) => !isOpen);
  }

  protected closeMenu(): void {
    this.menuOpen.set(false);
  }
}