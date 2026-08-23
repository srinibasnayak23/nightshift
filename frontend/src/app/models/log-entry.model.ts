export type LogLevel = 'info' | 'warn' | 'error';

export interface RawLogPayload {
  timestamp?: string;
  service?: string;
  level?: string;
  message?: string;
  [key: string]: unknown;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  displayTime: string;
  service: string;
  level: LogLevel;
  message: string;
  rawTimestamp: number;
  isNew?: boolean;
}

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected' | 'reconnecting';

export interface ConnectionState {
  status: ConnectionStatus;
  url: string;
  retryCount: number;
  retryCountdown: number;
  lastConnectedAt?: Date;
  lastError?: string;
}

export interface LogFilter {
  search: string;
  level: LogLevel | 'all';
  service: string;
}

export interface LogMetrics {
  total: number;
  info: number;
  warn: number;
  error: number;
  services: string[];
}
