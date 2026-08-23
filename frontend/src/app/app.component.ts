import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HeaderComponent } from './components/header/header.component';
import { MetricsBarComponent } from './components/metrics-bar/metrics-bar.component';
import { LogFilterComponent } from './components/log-filter/log-filter.component';
import { LogTableComponent } from './components/log-table/log-table.component';
import { ThinkingTerminalComponent } from './components/thinking-terminal/thinking-terminal.component';

export type DashboardViewMode = 'split' | 'logs' | 'agent';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    HeaderComponent,
    MetricsBarComponent,
    LogFilterComponent,
    LogTableComponent,
    ThinkingTerminalComponent,
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
})
export class AppComponent {
  title = 'Nightshift AI SRE - Live Observer & Reasoning Terminal';
  public readonly viewMode = signal<DashboardViewMode>('split');

  public setViewMode(mode: DashboardViewMode): void {
    this.viewMode.set(mode);
  }
}
