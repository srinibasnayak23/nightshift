import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AgentStreamService } from '../../services/agent-stream.service';
import { AgentNodeStatus, IncidentTrace } from '../../models/agent-thought.model';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-thinking-terminal',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './thinking-terminal.component.html',
  styleUrls: ['./thinking-terminal.component.css'],
})
export class ThinkingTerminalComponent {
  public readonly agentService = inject(AgentStreamService);

  // Expanded git diffs state
  public showDiff = signal<boolean>(false);
  public showSettings = false;
  public customUrl = `${environment.wsBaseUrl}/ws/agent-thoughts`;

  public toggleDiff(): void {
    this.showDiff.update((v) => !v);
  }

  public toggleAnomalyFilter(): void {
    this.agentService.filterAnomalyOnly.update((v) => !v);
  }

  public toggleSettings(): void {
    this.showSettings = !this.showSettings;
    if (this.showSettings) {
      this.customUrl = this.agentService.connectionState().url;
    }
  }

  public applyCustomUrl(): void {
    if (this.customUrl.trim()) {
      this.agentService.setUrl(this.customUrl.trim());
    }
    this.showSettings = false;
  }

  public getConfidenceClass(score?: number): string {
    if (score === undefined || score === null) return 'confidence-none';
    if (score >= 0.8) return 'confidence-high';
    if (score >= 0.5) return 'confidence-medium';
    return 'confidence-low';
  }

  public getConfidenceLabel(score?: number): string {
    if (score === undefined || score === null) return 'N/A';
    if (score >= 0.8) return 'High Confidence';
    if (score >= 0.5) return 'Moderate Confidence';
    return 'Low Confidence';
  }

  public getConfidencePercent(score?: number): number {
    if (score === undefined || score === null) return 0;
    return Math.round(score * 100);
  }

  public getStepStatusClass(status: AgentNodeStatus): string {
    switch (status) {
      case 'running':
        return 'step-running';
      case 'completed':
        return 'step-completed';
      case 'skipped':
        return 'step-skipped';
      case 'error':
        return 'step-error';
      default:
        return 'step-pending';
    }
  }

  public formatTimestamp(isoStr?: string): string {
    if (!isoStr) return '--:--:--';
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return isoStr;
    }
  }
}
