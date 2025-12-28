import { ComponentFixture, TestBed } from '@angular/core/testing';

import { VoiceConsoleComponent } from './voice-console.component';

describe('VoiceConsoleComponent', () => {
  let component: VoiceConsoleComponent;
  let fixture: ComponentFixture<VoiceConsoleComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [VoiceConsoleComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(VoiceConsoleComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
