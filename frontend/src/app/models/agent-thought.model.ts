import { ConnectionState } from './log-entry.model';

export type AgentNodeName = 'filter_node' | 'summarize_node' | 'fetch_diff_node' | 'correlate_node';

export type AgentNodeStatus = 'pending' | 'running' | 'completed' | 'skipped' | 'error';

export interface AgentThoughtState {
  is_anomaly?: boolean;
  affected_service?: string;
  error_summary?: string;
  git_diff?: string;
  suspect_commit?: string;
  hypothesis?: string;
  confidence?: number;
  [key: string]: unknown;
}

export interface AgentThoughtEvent {
  timestamp: string;
  node: AgentNodeName;
  status: 'started' | 'completed' | 'skipped' | 'error';
  thought: string;
  confidence?: number | null;
  state?: AgentThoughtState;
}

export interface TraceStep {
  node: AgentNodeName;
  displayName: string;
  status: AgentNodeStatus;
  thought?: string;
  timestamp?: string;
  displayTime?: string;
  details?: Record<string, unknown>;
}

export type TraceStatus = 'running' | 'completed' | 'nominal_stopped' | 'error';

export interface IncidentTrace {
  id: string;
  startedAt: string;
  completedAt?: string;
  service: string;
  status: TraceStatus;
  isAnomaly: boolean;
  steps: TraceStep[];
  errorSummary?: string;
  gitDiff?: string;
  suspectCommit?: string;
  hypothesis?: string;
  confidence?: number;
  isExpanded?: boolean;
}

export interface AgentStreamMetrics {
  totalTraces: number;
  anomaliesDetected: number;
  nominalSkipped: number;
  avgConfidence: number;
}
