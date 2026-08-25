import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HeaderComponent } from './components/header/header.component';
import { MetricsBarComponent } from './components/metrics-bar/metrics-bar.component';
import { LogFilterComponent } from './components/log-filter/log-filter.component';
import { LogTableComponent } from './components/log-table/log-table.component';
import { ThinkingTerminalComponent } from './components/thinking-terminal/thinking-terminal.component';
import { PendingApprovalsComponent } from './components/pending-approvals/pending-approvals.component';
import { ApprovalStreamService } from './services/approval-stream.service';

export type DashboardViewMode = 'split' | 'logs' | 'agent' | 'approvals';

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
    PendingApprovalsComponent,
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
})
export class AppComponent {
  title = 'Nightshift AI SRE - Live Observer, Reasoning & Remediation Platform';
  public readonly viewMode = signal<DashboardViewMode>('split');
  public readonly approvalService = inject(ApprovalStreamService);

  public setViewMode(mode: DashboardViewMode): void {
    this.viewMode.set(mode);
  }
}
