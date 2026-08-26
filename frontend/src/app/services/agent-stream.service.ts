import { Injectable, computed, signal } from '@angular/core';
import { ConnectionState, ConnectionStatus } from '../models/log-entry.model';
import {
  AgentNodeName,
  AgentStreamMetrics,
  AgentThoughtEvent,
  IncidentTrace,
  TraceStep,
} from '../models/agent-thought.model';
import { environment } from '../../environments/environment';

const DEFAULT_AGENT_WS_URL = `${environment.wsBaseUrl}/ws/agent-thoughts`;
const MAX_TRACE_HISTORY = 50;
const RECONNECT_INTERVAL_SECONDS = 3;

const INITIAL_STEPS_TEMPLATE: { node: AgentNodeName; displayName: string }[] = [
  { node: 'filter_node', displayName: '1. Anomaly Filter (Cost Gate)' },
  { node: 'summarize_node', displayName: '2. Error Diagnosis & Extraction' },
  { node: 'fetch_diff_node', displayName: '3. GitHub Diff & Commit Tool' },
  { node: 'correlate_node', displayName: '4. Root-Cause Hypothesis & Confidence' },
];

@Injectable({
  providedIn: 'root',
})
export class AgentStreamService {
  // Traces list (newest first)
  private readonly _traces = signal<IncidentTrace[]>([]);
  public readonly traces = this._traces.asReadonly();

  // Connection State
  private readonly _connectionState = signal<ConnectionState>({
    status: 'connecting',
    url: DEFAULT_AGENT_WS_URL,
    retryCount: 0,
    retryCountdown: RECONNECT_INTERVAL_SECONDS,
  });
  public readonly connectionState = this._connectionState.asReadonly();

  // Filter & UI Signals
  public readonly filterAnomalyOnly = signal<boolean>(false);
  public readonly isSimulating = signal<boolean>(false);

  // Selected or Active Trace ID for focused inspection
  public readonly selectedTraceId = signal<string | null>(null);

  // Computed: Filtered Traces
  public readonly filteredTraces = computed(() => {
    const all = this._traces();
    const anomalyOnly = this.filterAnomalyOnly();
    if (!anomalyOnly) return all;
    return all.filter((t) => t.isAnomaly);
  });

  // Computed: Current Active (or most recent) Trace
  public readonly activeTrace = computed<IncidentTrace | null>(() => {
    const selectedId = this.selectedTraceId();
    const all = this._traces();
    if (selectedId) {
      const found = all.find((t) => t.id === selectedId);
      if (found) return found;
    }
    return all.length > 0 ? all[0] : null;
  });

  // Computed: Stream Metrics
  public readonly metrics = computed<AgentStreamMetrics>(() => {
    const all = this._traces();
    const anomalies = all.filter((t) => t.isAnomaly);
    const nominal = all.filter((t) => t.status === 'nominal_stopped');

    const totalConfidence = anomalies.reduce((acc, t) => acc + (t.confidence || 0), 0);
    const avgConfidence = anomalies.length > 0 ? totalConfidence / anomalies.length : 0;

    return {
      totalTraces: all.length,
      anomaliesDetected: anomalies.length,
      nominalSkipped: nominal.length,
      avgConfidence: Math.round(avgConfidence * 100),
    };
  });

  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setInterval> | null = null;
  private isExplicitlyClosed = false;
  private simulationTimeouts: ReturnType<typeof setTimeout>[] = [];

  constructor() {
    this.connect(DEFAULT_AGENT_WS_URL);
  }

  /**
   * Connect to WebSocket
   */
  public connect(url: string = DEFAULT_AGENT_WS_URL): void {
    this.isExplicitlyClosed = false;
    this.clearReconnectTimer();
    this.cleanupSocket();

    this.updateConnectionState({
      status: 'connecting',
      url,
      lastError: undefined,
    });

    try {
      this.socket = new WebSocket(url);

      this.socket.onopen = () => {
        this.updateConnectionState({
          status: 'connected',
          retryCount: 0,
          retryCountdown: RECONNECT_INTERVAL_SECONDS,
          lastConnectedAt: new Date(),
          lastError: undefined,
        });
      };

      this.socket.onmessage = (event: MessageEvent) => {
        this.handleIncomingRawEvent(event.data);
      };

      this.socket.onerror = () => {
        this.updateConnectionState({
          lastError: 'WebSocket connection error on agent-thoughts stream',
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

  public disconnect(): void {
    this.isExplicitlyClosed = true;
    this.clearReconnectTimer();
    this.cleanupSocket();
    this.updateConnectionState({
      status: 'disconnected',
      retryCountdown: 0,
    });
  }

  public retryNow(): void {
    this.clearReconnectTimer();
    this.connect(this._connectionState().url);
  }

  public setUrl(newUrl: string): void {
    if (newUrl !== this._connectionState().url) {
      this.connect(newUrl);
    }
  }

  public toggleTrace(id: string): void {
    this._traces.update((list) =>
      list.map((t) => (t.id === id ? { ...t, isExpanded: !t.isExpanded } : t))
    );
    this.selectedTraceId.set(id);
  }

  public clearTraces(): void {
    this._traces.set([]);
    this.selectedTraceId.set(null);
  }

  // --- Thought Aggregation Logic ---

  private handleIncomingRawEvent(data: unknown): void {
    try {
      let parsed: AgentThoughtEvent;
      if (typeof data === 'string') {
        parsed = JSON.parse(data);
      } else {
        parsed = data as AgentThoughtEvent;
      }
      this.processThoughtEvent(parsed);
    } catch {
      // Ignore unparseable frames
    }
  }

  public processThoughtEvent(event: AgentThoughtEvent): void {
    const traces = [...this._traces()];
    let active = traces.length > 0 && traces[0].status === 'running' ? traces[0] : null;

    // Check if this event starts a new trace (filter_node event or no active running trace)
    if (event.node === 'filter_node' && (!active || event.status === 'started' || event.status === 'completed' || event.status === 'skipped')) {
      const serviceName = this.extractService(event);
      const isNominal = event.status === 'skipped' || event.state?.is_anomaly === false;

      const newTrace: IncidentTrace = {
        id: 'trace_' + Date.now() + '_' + Math.random().toString(36).substring(2, 6),
        startedAt: event.timestamp || new Date().toISOString(),
        service: serviceName,
        status: isNominal ? 'nominal_stopped' : 'running',
        isAnomaly: !isNominal,
        isExpanded: true,
        steps: this.createInitialSteps(event),
      };

      // Collapse older traces
      const updatedList = [newTrace, ...traces.map((t) => ({ ...t, isExpanded: false }))].slice(
        0,
        MAX_TRACE_HISTORY
      );

      this._traces.set(updatedList);
      this.selectedTraceId.set(newTrace.id);
      return;
    }

    if (!active) {
      // Create a recovery trace if mid-stream event received
      active = {
        id: 'trace_' + Date.now(),
        startedAt: event.timestamp || new Date().toISOString(),
        service: this.extractService(event),
        status: 'running',
        isAnomaly: true,
        isExpanded: true,
        steps: this.createInitialSteps(),
      };
      traces.unshift(active);
    }

    // Update existing active trace steps
    const updatedSteps = active.steps.map((step) => {
      if (step.node === event.node) {
        return {
          ...step,
          status: event.status === 'started' ? 'running' : (event.status as any),
          thought: event.thought || step.thought,
          timestamp: event.timestamp || new Date().toISOString(),
          displayTime: this.formatTime(new Date(event.timestamp || Date.now())),
        };
      }
      return step;
    });

    // Update state fields from payload
    const state = event.state || {};
    const isAnomaly = state.is_anomaly !== undefined ? Boolean(state.is_anomaly) : active.isAnomaly;
    let traceStatus = active.status;

    if (event.node === 'filter_node' && (event.status === 'skipped' || state.is_anomaly === false)) {
      traceStatus = 'nominal_stopped';
      // Mark downstream steps as skipped
      updatedSteps.forEach((s, idx) => {
        if (idx > 0) s.status = 'skipped';
      });
    } else if (event.node === 'correlate_node' && event.status === 'completed') {
      traceStatus = 'completed';
    }

    const updatedTrace: IncidentTrace = {
      ...active,
      status: traceStatus,
      isAnomaly,
      steps: updatedSteps,
      errorSummary: state.error_summary || active.errorSummary,
      gitDiff: state.git_diff || active.gitDiff,
      suspectCommit: state.suspect_commit || active.suspectCommit,
      hypothesis: state.hypothesis || active.hypothesis,
      confidence: event.confidence !== undefined && event.confidence !== null ? event.confidence : (state.confidence ?? active.confidence),
      completedAt: traceStatus !== 'running' ? event.timestamp || new Date().toISOString() : undefined,
    };

    traces[0] = updatedTrace;
    this._traces.set(traces);
  }

  private createInitialSteps(initialEvent?: AgentThoughtEvent): TraceStep[] {
    return INITIAL_STEPS_TEMPLATE.map((tpl) => {
      let status: any = 'pending';
      let thought: string | undefined = undefined;

      if (initialEvent && initialEvent.node === tpl.node) {
        status = initialEvent.status === 'started' ? 'running' : initialEvent.status;
        thought = initialEvent.thought;
      }

      return {
        node: tpl.node,
        displayName: tpl.displayName,
        status,
        thought,
      };
    });
  }

  private extractService(event: AgentThoughtEvent): string {
    const stateService = event.state?.['affected_service'] ?? event.state?.affected_service;
    if (stateService) return String(stateService);
    const thought = event.thought || '';
    const match = thought.match(/\[(.*?)\]/);
    if (match && match[1]) return match[1];
    return 'payment-gateway';
  }

  private formatTime(d: Date): string {
    return d.toTimeString().split(' ')[0] + '.' + String(d.getMilliseconds()).padStart(3, '0');
  }

  // --- Offline Simulation for Frontend Preview ---

  public toggleSimulation(): void {
    if (this.isSimulating()) {
      this.stopSimulation();
    } else {
      this.startSimulation();
    }
  }

  private startSimulation(): void {
    this.isSimulating.set(true);
    this.runSimulatedIncident(true); // anomalous incident
  }

  public stopSimulation(): void {
    this.isSimulating.set(false);
    this.simulationTimeouts.forEach((t) => clearTimeout(t));
    this.simulationTimeouts = [];
  }

  public runSimulatedIncident(isAnomaly = true): void {
    const services = ['payment-gateway', 'order-processor', 'auth-service', 'inventory-api'];
    const service = services[Math.floor(Math.random() * services.length)];
    const commitSha = Math.random().toString(16).substring(2, 9);

    if (!isAnomaly) {
      // Simulate Nominal Pass
      this.processThoughtEvent({
        timestamp: new Date().toISOString(),
        node: 'filter_node',
        status: 'skipped',
        thought: `Log from [${service}] is nominal (level: info). Bypassing LLM pipeline.`,
        state: { is_anomaly: false },
      });
      return;
    }

    // Step 1: Filter
    this.processThoughtEvent({
      timestamp: new Date().toISOString(),
      node: 'filter_node',
      status: 'completed',
      thought: `Anomaly detected in log from [${service}] (level: error). Escalating to LLM reasoning.`,
      state: { is_anomaly: true, affected_service: service },
    });

    // Step 2: Summarize
    const t1 = setTimeout(() => {
      this.processThoughtEvent({
        timestamp: new Date().toISOString(),
        node: 'summarize_node',
        status: 'completed',
        thought: `Error diagnosed: [DatabaseDeadlock] Service: ${service} | Component: db-pool | Details: Deadlock during concurrent ledger update.`,
        state: {
          error_summary: `Database deadlock in ${service} connection pool during concurrent checkout transactions.`,
        },
      });
    }, 1200);

    // Step 3: Fetch Diff
    const t2 = setTimeout(() => {
      this.processThoughtEvent({
        timestamp: new Date().toISOString(),
        node: 'fetch_diff_node',
        status: 'completed',
        thought: `Fetched commit history from srinibasnayak23/nightshift. Suspect commit identified: [${commitSha}].`,
        state: {
          suspect_commit: commitSha,
          git_diff: `Commit ${commitSha}: Added unindexed foreign key in checkout transaction handler.\n- db.execute("UPDATE accounts SET balance = ...")\n+ db.execute("UPDATE accounts SET balance = ... FOR UPDATE")`,
        },
      });
    }, 2400);

    // Step 4: Correlate
    const t3 = setTimeout(() => {
      const conf = Number((0.82 + Math.random() * 0.15).toFixed(2));
      this.processThoughtEvent({
        timestamp: new Date().toISOString(),
        node: 'correlate_node',
        status: 'completed',
        thought: `Hypothesis generated (Confidence: ${(conf * 100).toFixed(0)}%): Deadlock introduced in commit ${commitSha} locking ledger rows in reversed order.`,
        confidence: conf,
        state: {
          hypothesis: `The incident was caused by commit ${commitSha} which introduced row-level locking (FOR UPDATE) in reversed order across concurrent transactions, triggering database deadlocks under load.`,
          confidence: conf,
        },
      });
    }, 3800);

    this.simulationTimeouts.push(t1, t2, t3);
  }

  // --- WebSocket Helpers ---

  private updateConnectionState(partial: Partial<ConnectionState>): void {
    this._connectionState.update((current) => ({ ...current, ...partial }));
  }

  private scheduleReconnect(url: string): void {
    this.clearReconnectTimer();
    let countdown = RECONNECT_INTERVAL_SECONDS;
    this.updateConnectionState({ retryCountdown: countdown });

    this.reconnectTimer = setInterval(() => {
      countdown -= 1;
      this.updateConnectionState({ retryCountdown: Math.max(0, countdown) });

      if (countdown <= 0) {
        this.clearReconnectTimer();
        this.connect(url);
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
      if (
        this.socket.readyState === WebSocket.OPEN ||
        this.socket.readyState === WebSocket.CONNECTING
      ) {
        this.socket.close();
      }
      this.socket = null;
    }
  }
}
