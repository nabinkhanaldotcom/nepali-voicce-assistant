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
