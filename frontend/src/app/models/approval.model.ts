import { ConnectionState } from './log-entry.model';

export type ActionType = 'restart' | 'rollback' | 'commit_fix' | 'none';

export type DecisionType = 'approved' | 'rejected';

export interface ProposedFix {
  file_path: string;
  code_patch: string;
  updated_file_content?: string;
  commit_message: string;
  explanation: string;
  blob_sha?: string;
}

export type ApprovalCardStatus =
  | 'pending'
  | 'confirming'
  | 'submitting'
  | 'executed'
  | 'failed'
  | 'rejected';

export interface PendingApprovalEvent {
  incident_id: string;
  timestamp: string;
  service: string;
  error_summary: string;
  hypothesis: string;
  confidence: number;
  suspect_commit: string;
  action_type: ActionType;
  proposed_fix?: ProposedFix | null;
  status: string;
}

export interface DecisionDetails {
  status?: string;
  action?: string;
  timestamp?: string;
  details?: {
    success?: boolean;
    service_id?: string;
    commit_id?: string;
    commit_sha?: string;
    commit_url?: string;
    deploy_id?: string;
    status_code?: number;
    message?: string;
    error?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface DecisionResponse {
  incident_id: string;
  decision: DecisionType;
  status: 'executed' | 'rejected' | 'error';
  action_type?: ActionType;
  execution_result?: DecisionDetails | string | null;
  detail?: string;
}

export interface ApprovalItem {
  id: string;
  incidentId: string;
  timestamp: string;
  displayTime: string;
  service: string;
  errorSummary: string;
  hypothesis: string;
  confidence: number;
  suspectCommit: string;
  actionType: ActionType;
  proposedFix?: ProposedFix | null;
  status: ApprovalCardStatus;
  humanDecision?: DecisionType;
  resolvedAt?: string;
  displayResolvedTime?: string;
  executionResult?: DecisionDetails | null;
  errorMessage?: string;
  isConfirmingApprove?: boolean;
  isConfirmingReject?: boolean;
}

export interface ApprovalMetrics {
  totalPending: number;
  totalApproved: number;
  totalRejected: number;
  avgConfidence: number;
}
