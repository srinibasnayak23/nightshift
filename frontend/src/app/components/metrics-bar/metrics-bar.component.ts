import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LogStreamService } from '../../services/log-stream.service';
import { LogLevel } from '../../models/log-entry.model';

import { ApprovalStreamService } from '../../services/approval-stream.service';

@Component({
  selector: 'app-metrics-bar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './metrics-bar.component.html',
  styleUrls: ['./metrics-bar.component.css']
})
export class MetricsBarComponent {
  public readonly streamService = inject(LogStreamService);
  public readonly approvalService = inject(ApprovalStreamService);

  public setFilterLevel(level: LogLevel | 'all'): void {
    const current = this.streamService.filter().level;
    if (current === level && level !== 'all') {
      this.streamService.updateFilter({ level: 'all' });
    } else {
      this.streamService.updateFilter({ level });
    }
  }
}
