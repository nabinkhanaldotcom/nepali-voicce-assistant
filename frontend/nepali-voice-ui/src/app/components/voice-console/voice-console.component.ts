import { Component, OnDestroy, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { VoiceService, SttResponse } from '../../services/voice.service';

@Component({
  selector: 'app-voice-console',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './voice-console.component.html',
  styleUrl: './voice-console.component.scss'
})
export class VoiceConsoleComponent implements OnDestroy {

  isRecording = false;
  isSttLoading = false;
  isTtsLoading = false;

  recognizedText = '';
  errorMessage = '';

  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  lastRecordedBlob: Blob | null = null;

  recordedAudioUrl: string | null = null;  // original recording
  replyAudioUrl: string | null = null;     // AI reply audio

  constructor(private voiceService: VoiceService, private ngZone: NgZone) {}

  // ---- RECORDING ----

  startRecording(): void {
    this.errorMessage = '';

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.errorMessage = 'getUserMedia is not supported in this browser.';
      return;
    }

    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((stream: MediaStream) => {
        this.audioChunks = [];
        this.mediaRecorder = new MediaRecorder(stream);

        this.mediaRecorder.ondataavailable = (event: BlobEvent) => {
          if (event.data && event.data.size > 0) {
            this.audioChunks.push(event.data);
          }
        };

        // this.mediaRecorder.onstop = () => {
        //   const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
        //   this.lastRecordedBlob = audioBlob;

        //   // Create URL for original recording preview
        //   if (this.recordedAudioUrl) {
        //     URL.revokeObjectURL(this.recordedAudioUrl);
        //   }
        //   this.recordedAudioUrl = URL.createObjectURL(audioBlob);
        // };

        this.mediaRecorder.onstop = () => {
          const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
        
          this.ngZone.run(() => {  // 👈 wrap state changes in zone.run
            this.lastRecordedBlob = audioBlob;
        
            if (this.recordedAudioUrl) {
              URL.revokeObjectURL(this.recordedAudioUrl);
            }
            this.recordedAudioUrl = URL.createObjectURL(audioBlob);
          });
        };
        

        this.mediaRecorder.start();
        this.isRecording = true;
      })
      .catch((err: unknown) => {
        console.error('Error accessing microphone', err);
        this.errorMessage = 'Could not access microphone. Check permissions.';
      });
  }

  stopRecording(): void {
    if (this.mediaRecorder && this.isRecording) {
      this.mediaRecorder.stop();
      this.mediaRecorder.stream.getTracks().forEach((track: MediaStreamTrack) => track.stop());
      this.isRecording = false;
    }
  }

  // ---- STT (Speech to Text) ----

  sendToStt(): void {
    this.errorMessage = '';

    if (!this.lastRecordedBlob) {
      this.errorMessage = 'No recording available. Please record first.';
      return;
    }

    this.isSttLoading = true;
    this.voiceService.stt(this.lastRecordedBlob).subscribe({
      next: (res: SttResponse) => {
        this.recognizedText = res.text || '';
        this.isSttLoading = false;
      },
      error: (err: unknown) => {
        console.error('STT error', err);
        this.errorMessage = 'Error during speech-to-text.';
        this.isSttLoading = false;
      }
    });
  }

  // ---- TTS (Text to Speech) ----

  speakRecognizedText(): void {
    this.errorMessage = '';

    const text = this.recognizedText?.trim();
    if (!text) {
      this.errorMessage = 'No text to speak. Use STT or type something.';
      return;
    }

    this.isTtsLoading = true;
    this.voiceService.tts(text).subscribe({
      next: (audioBlob: Blob) => {
        if (this.replyAudioUrl) {
          URL.revokeObjectURL(this.replyAudioUrl);
        }

        this.replyAudioUrl = URL.createObjectURL(audioBlob);
        this.isTtsLoading = false;

        // Auto-play the reply audio
        const audio = new Audio(this.replyAudioUrl);
        audio.play().catch((err: unknown) => {
          console.warn('Auto-play blocked:', err);
        });
      },
      error: (err: unknown) => {
        console.error('TTS error', err);
        this.errorMessage = 'Error during text-to-speech.';
        this.isTtsLoading = false;
      }
    });
  }

  // Cleanup URLs on destroy
  ngOnDestroy(): void {
    if (this.recordedAudioUrl) {
      URL.revokeObjectURL(this.recordedAudioUrl);
    }
    if (this.replyAudioUrl) {
      URL.revokeObjectURL(this.replyAudioUrl);
    }
  }
}
