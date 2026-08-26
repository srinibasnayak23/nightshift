import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApprovalStreamService } from '../../services/approval-stream.service';
import { ActionType, ApprovalItem, DecisionType } from '../../models/approval.model';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-pending-approvals',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './pending-approvals.component.html',
  styleUrls: ['./pending-approvals.component.css'],
})
export class PendingApprovalsComponent {
  public readonly approvalService = inject(ApprovalStreamService);

  public showSettings = false;
  public customUrl = `${environment.wsBaseUrl}/ws/pending-approvals`;
  public githubRepo = 'srinibasnayak23/BloHelp';

  public toggleSettings(): void {
    this.showSettings = !this.showSettings;
    if (this.showSettings) {
      this.customUrl = this.approvalService.connectionState().url;
    }
  }

  public applyCustomUrl(): void {
    if (this.customUrl.trim()) {
      this.approvalService.setUrl(this.customUrl.trim());
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

  public getCommitUrl(commitSha?: string): string {
    if (!commitSha || commitSha === 'unknown' || commitSha === 'none') {
      return `https://github.com/${this.githubRepo}`;
    }
    return `https://github.com/${this.githubRepo}/commit/${commitSha}`;
  }

  public onApproveClick(item: ApprovalItem): void {
    this.approvalService.requestApproveConfirmation(item.incidentId);
  }

  public onRejectClick(item: ApprovalItem): void {
    this.approvalService.requestRejectConfirmation(item.incidentId);
  }

  public onCancelConfirmation(item: ApprovalItem): void {
    this.approvalService.cancelConfirmation(item.incidentId);
  }

  public onConfirmDecision(item: ApprovalItem, decision: DecisionType): void {
    this.approvalService.submitDecision(item.incidentId, decision);
  }

  public triggerSimulation(type: ActionType): void {
    this.approvalService.simulatePendingApproval(type);
  }

  public formatIso(iso?: string): string {
    if (!iso) return '--:--:--';
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return iso;
    }
  }
}
