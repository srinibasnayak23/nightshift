import { Injectable, computed, signal } from '@angular/core';
import { ConnectionState } from '../models/log-entry.model';
import {
  ActionType,
  ApprovalItem,
  ApprovalMetrics,
  DecisionDetails,
  DecisionResponse,
  DecisionType,
  PendingApprovalEvent,
} from '../models/approval.model';
import { environment } from '../../environments/environment';

const DEFAULT_APPROVALS_WS_URL = `${environment.wsBaseUrl}/ws/pending-approvals`;
const DEFAULT_API_BASE_URL = environment.apiBaseUrl;
const RECONNECT_INTERVAL_SECONDS = 3;

@Injectable({
  providedIn: 'root',
})
export class ApprovalStreamService {
  // Active Pending Approvals (waiting for human decision)
  private readonly _pendingApprovals = signal<ApprovalItem[]>([]);
  public readonly pendingApprovals = this._pendingApprovals.asReadonly();

  // Resolved Decision History (most recent first)
  private readonly _historyApprovals = signal<ApprovalItem[]>([]);
  public readonly historyApprovals = this._historyApprovals.asReadonly();

  // WebSocket Connection State
  private readonly _connectionState = signal<ConnectionState>({
    status: 'connecting',
    url: DEFAULT_APPROVALS_WS_URL,
    retryCount: 0,
    retryCountdown: RECONNECT_INTERVAL_SECONDS,
  });
  public readonly connectionState = this._connectionState.asReadonly();

  // Computed metrics
  public readonly pendingCount = computed(() => this._pendingApprovals().length);

  public readonly metrics = computed<ApprovalMetrics>(() => {
    const pending = this._pendingApprovals();
    const history = this._historyApprovals();
    const totalApproved = history.filter((h) => h.humanDecision === 'approved').length;
    const totalRejected = history.filter((h) => h.humanDecision === 'rejected').length;

    const all = [...pending, ...history];
    const avgConfidence =
      all.length > 0
        ? Math.round((all.reduce((acc, curr) => acc + (curr.confidence || 0), 0) / all.length) * 100)
        : 0;

    return {
      totalPending: pending.length,
      totalApproved,
      totalRejected,
      avgConfidence,
    };
  });

  // Socket & Reconnect Timer references
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setInterval> | null = null;
  private isExplicitlyClosed = false;

  constructor() {
    this.connect(DEFAULT_APPROVALS_WS_URL);
    this.fetchInitialPendingApprovals();
  }

  /**
   * Connect to Pending Approvals WebSocket
   */
  public connect(url: string = DEFAULT_APPROVALS_WS_URL): void {
    this.cleanupSocket();
    this.isExplicitlyClosed = false;

    this.updateConnectionState({
      status: 'connecting',
      url,
      lastError: undefined,
    });

    try {
      this.socket = new WebSocket(url);

      this.socket.onopen = () => {
        this.clearReconnectTimer();
        this.updateConnectionState({
          status: 'connected',
          retryCount: 0,
          retryCountdown: RECONNECT_INTERVAL_SECONDS,
          lastConnectedAt: new Date(),
          lastError: undefined,
        });
      };

      this.socket.onmessage = (event: MessageEvent) => {
        this.handleIncomingRawMessage(event.data);
      };

      this.socket.onerror = () => {
        this.updateConnectionState({
          lastError: 'Approvals WebSocket connection error',
        });
      };

      this.socket.onclose = () => {
        if (this.isExplicitlyClosed) return;

        const isReconnecting = this._connectionState().status !== 'connected';
        this.updateConnectionState({
          status: isReconnecting ? 'reconnecting' : 'disconnected',
          retryCount: this._connectionState().retryCount + 1,
        });

        this.scheduleReconnect(url);
      };
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown connection error';
      this.updateConnectionState({
        status: 'disconnected',
        lastError: errorMessage,
      });
      this.scheduleReconnect(url);
    }
  }

  /**
   * Disconnect manually
   */
  public disconnect(): void {
    this.isExplicitlyClosed = true;
    this.clearReconnectTimer();
    this.cleanupSocket();
    this.updateConnectionState({
      status: 'disconnected',
      retryCountdown: 0,
    });
  }

  /**
   * Retry connection immediately
   */
  public retryNow(): void {
    this.clearReconnectTimer();
    this.connect(this._connectionState().url);
    this.fetchInitialPendingApprovals();
  }

  /**
   * Set target WebSocket URL
   */
  public setUrl(newUrl: string): void {
    if (newUrl !== this._connectionState().url) {
      this.connect(newUrl);
    }
  }

  /**
   * Fetch initial pending approvals from REST API on startup
   */
  public async fetchInitialPendingApprovals(): Promise<void> {
    try {
      const apiUrl = `${DEFAULT_API_BASE_URL}/incidents/pending`;
      const response = await fetch(apiUrl);
      if (response.ok) {
        const data = await response.json();
        const pendingList = data.pending_incidents || [];
        for (const item of pendingList) {
          this.addPendingApproval(this.normalizeApprovalEvent(item));
        }
      }
    } catch {
      // Backend may be offline during local startup - ignore gracefully
    }
  }

  /**
   * Request confirmation step before executing decision
   */
  public requestApproveConfirmation(incidentId: string): void {
    this._pendingApprovals.update((items) =>
      items.map((item) =>
        item.incidentId === incidentId
          ? { ...item, isConfirmingApprove: true, isConfirmingReject: false }
          : item
      )
    );
  }

  public requestRejectConfirmation(incidentId: string): void {
    this._pendingApprovals.update((items) =>
      items.map((item) =>
        item.incidentId === incidentId
          ? { ...item, isConfirmingReject: true, isConfirmingApprove: false }
          : item
      )
    );
  }

  public cancelConfirmation(incidentId: string): void {
    this._pendingApprovals.update((items) =>
      items.map((item) =>
        item.incidentId === incidentId
          ? { ...item, isConfirmingApprove: false, isConfirmingReject: false }
          : item
      )
    );
  }

  /**
   * Submit decision (approved / rejected) to backend REST API
   * POST /incidents/{incident_id}/decision
   */
  public async submitDecision(
    incidentId: string,
    decision: DecisionType
  ): Promise<DecisionResponse | null> {
    // Set item status to 'submitting'
    this._pendingApprovals.update((items) =>
      items.map((item) =>
        item.incidentId === incidentId
          ? { ...item, status: 'submitting', isConfirmingApprove: false, isConfirmingReject: false }
          : item
      )
    );

    const targetItem = this._pendingApprovals().find((i) => i.incidentId === incidentId);

    try {
      const url = `${DEFAULT_API_BASE_URL}/incidents/${incidentId}/decision`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision }),
      });

      const now = new Date();
      const resolvedIso = now.toISOString();
      const displayTime = this.formatDisplayTime(now);

      if (response.ok) {
        const data: DecisionResponse = await response.json();
        const parsedExecution: DecisionDetails | null =
          typeof data.execution_result === 'string'
            ? JSON.parse(data.execution_result)
            : (data.execution_result as DecisionDetails | null);

        const resolvedItem: ApprovalItem = {
          ...(targetItem || this.createFallbackItem(incidentId, decision)),
          status: decision === 'approved' ? 'executed' : 'rejected',
          humanDecision: decision,
          resolvedAt: resolvedIso,
          displayResolvedTime: displayTime,
          executionResult: parsedExecution,
        };

        // Remove from pending, add to history (most recent first)
        this.resolveItemToHistory(incidentId, resolvedItem);
        return data;
      } else {
        const errorText = await response.text();
        const failedItem: ApprovalItem = {
          ...(targetItem || this.createFallbackItem(incidentId, decision)),
          status: 'failed',
          humanDecision: decision,
          resolvedAt: resolvedIso,
          displayResolvedTime: displayTime,
          errorMessage: `HTTP ${response.status}: ${errorText || response.statusText}`,
        };

        this.resolveItemToHistory(incidentId, failedItem);
        return null;
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Network error submitting decision';
      const now = new Date();
      const failedItem: ApprovalItem = {
        ...(targetItem || this.createFallbackItem(incidentId, decision)),
        status: 'failed',
        humanDecision: decision,
        resolvedAt: now.toISOString(),
        displayResolvedTime: this.formatDisplayTime(now),
        errorMessage: errorMsg,
      };

      this.resolveItemToHistory(incidentId, failedItem);
      return null;
    }
  }

  /**
   * Clear historical decision log
   */
  public clearHistory(): void {
    this._historyApprovals.set([]);
  }

  /**
   * Development simulator: Trigger a synthetic pending approval card
   */
  public simulatePendingApproval(type: ActionType = 'restart'): void {
    const isRestart = type === 'restart';
    const fakeId = `inc-sim-${Math.random().toString(36).substring(2, 6)}`;
    const mockItem: ApprovalItem = {
      id: fakeId,
      incidentId: fakeId,
      timestamp: new Date().toISOString(),
      displayTime: this.formatDisplayTime(new Date()),
      service: 'BloHelp',
      errorSummary: isRestart
        ? 'Fatal connection pool timeout and memory leak in database driver'
        : 'NullPointerException in OAuth token signature validator',
      hypothesis: isRestart
        ? 'Worker process memory exhaustion due to unclosed database cursor pool under load. Service restart required.'
        : 'Regression introduced in commit 7f2a18b modifying JWT header decoding logic. Rollback recommended.',
      confidence: isRestart ? 0.88 : 0.94,
      suspectCommit: isRestart ? 'unknown' : '7f2a18b',
      actionType: type,
      status: 'pending',
      isConfirmingApprove: false,
      isConfirmingReject: false,
    };

    this.addPendingApproval(mockItem);
  }

  // Private Helper Methods

  private handleIncomingRawMessage(data: unknown): void {
    try {
      let parsed: PendingApprovalEvent;
      if (typeof data === 'string') {
        parsed = JSON.parse(data);
      } else {
        parsed = data as PendingApprovalEvent;
      }

      if (parsed && parsed.incident_id) {
        const item = this.normalizeApprovalEvent(parsed);
        this.addPendingApproval(item);
      }
    } catch {
      // Ignore non-JSON broadcast packets
    }
  }

  private normalizeApprovalEvent(event: PendingApprovalEvent): ApprovalItem {
    const now = new Date();
    const dateObj = event.timestamp ? new Date(event.timestamp) : now;
    const validDate = isNaN(dateObj.getTime()) ? now : dateObj;

    return {
      id: event.incident_id,
      incidentId: event.incident_id,
      timestamp: validDate.toISOString(),
      displayTime: this.formatDisplayTime(validDate),
      service: event.service || 'BloHelp',
      errorSummary: event.error_summary || 'Service diagnostic anomaly detected',
      hypothesis: event.hypothesis || 'Root-cause hypothesis generated by reasoning engine',
      confidence: typeof event.confidence === 'number' ? event.confidence : 0.85,
      suspectCommit: event.suspect_commit || 'unknown',
      actionType: event.action_type || 'restart',
      proposedFix: event.proposed_fix || null,
      status: 'pending',
      isConfirmingApprove: false,
      isConfirmingReject: false,
    };
  }

  private addPendingApproval(item: ApprovalItem): void {
    this._pendingApprovals.update((current) => {
      // Deduplicate by incidentId
      const exists = current.some((i) => i.incidentId === item.incidentId);
      if (exists) {
        return current.map((i) => (i.incidentId === item.incidentId ? { ...i, ...item } : i));
      }
      return [item, ...current];
    });
  }

  private resolveItemToHistory(incidentId: string, resolvedItem: ApprovalItem): void {
    this._pendingApprovals.update((items) => items.filter((i) => i.incidentId !== incidentId));
    this._historyApprovals.update((history) => [resolvedItem, ...history]);
  }

  private createFallbackItem(incidentId: string, decision: DecisionType): ApprovalItem {
    const now = new Date();
    return {
      id: incidentId,
      incidentId,
      timestamp: now.toISOString(),
      displayTime: this.formatDisplayTime(now),
      service: 'BloHelp',
      errorSummary: 'Incident remediation request',
      hypothesis: 'Remediation decision processed by operator',
      confidence: 0.85,
      suspectCommit: 'unknown',
      actionType: 'restart',
      status: decision === 'approved' ? 'executed' : 'rejected',
    };
  }

  private formatDisplayTime(date: Date): string {
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    return `${hours}:${minutes}:${seconds}`;
  }

  private scheduleReconnect(url: string): void {
    this.clearReconnectTimer();

    let remainingSeconds = RECONNECT_INTERVAL_SECONDS;
    this.updateConnectionState({
      status: 'reconnecting',
      retryCountdown: remainingSeconds,
    });

    this.reconnectTimer = setInterval(() => {
      remainingSeconds--;
      if (remainingSeconds <= 0) {
        this.clearReconnectTimer();
        this.connect(url);
      } else {
        this.updateConnectionState({
          retryCountdown: remainingSeconds,
        });
      }
    }, 1000);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearInterval(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private cleanupSocket(): void {
    if (this.socket) {
      this.socket.onopen = null;
      this.socket.onmessage = null;
      this.socket.onerror = null;
      this.socket.onclose = null;
      try {
        this.socket.close();
      } catch {
        // Ignore close exceptions
      }
      this.socket = null;
    }
  }

  private updateConnectionState(partial: Partial<ConnectionState>): void {
    this._connectionState.update((current) => ({ ...current, ...partial }));
  }
}
