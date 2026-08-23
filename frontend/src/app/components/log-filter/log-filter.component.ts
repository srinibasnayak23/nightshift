import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LogStreamService } from '../../services/log-stream.service';
import { LogLevel } from '../../models/log-entry.model';

@Component({
  selector: 'app-log-filter',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './log-filter.component.html',
  styleUrls: ['./log-filter.component.css']
})
export class LogFilterComponent {
  public readonly streamService = inject(LogStreamService);

  public onSearchChange(term: string): void {
    this.streamService.updateFilter({ search: term });
  }

  public setLevel(level: LogLevel | 'all'): void {
    this.streamService.updateFilter({ level });
  }

  public onServiceChange(event: Event): void {
    const target = event.target as HTMLSelectElement;
    this.streamService.updateFilter({ service: target.value });
  }

  public clearSearch(): void {
    this.streamService.updateFilter({ search: '' });
  }
}
