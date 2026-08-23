import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LogStreamService } from '../../services/log-stream.service';
import { LogLevel } from '../../models/log-entry.model';

@Component({
  selector: 'app-metrics-bar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './metrics-bar.component.html',
  styleUrls: ['./metrics-bar.component.css']
})
export class MetricsBarComponent {
  public readonly streamService = inject(LogStreamService);

  public setFilterLevel(level: LogLevel | 'all'): void {
    const current = this.streamService.filter().level;
    if (current === level && level !== 'all') {
      this.streamService.updateFilter({ level: 'all' });
    } else {
      this.streamService.updateFilter({ level });
    }
  }
}
