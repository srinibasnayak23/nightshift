import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LogStreamService } from '../../services/log-stream.service';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './header.component.html',
  styleUrls: ['./header.component.css']
})
export class HeaderComponent {
  public readonly streamService = inject(LogStreamService);
  public showSettings = false;
  public customUrl = 'ws://localhost:8000/ws/logs';

  public toggleSettings(): void {
    this.showSettings = !this.showSettings;
    if (this.showSettings) {
      this.customUrl = this.streamService.connectionState().url;
    }
  }

  public applyCustomUrl(): void {
    this.streamService.setUrl(this.customUrl.trim());
    this.showSettings = false;
  }
}
