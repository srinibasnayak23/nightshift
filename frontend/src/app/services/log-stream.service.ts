import { Injectable, computed, signal } from '@angular/core';
import { ConnectionState, ConnectionStatus, LogEntry, LogFilter, LogLevel, LogMetrics, RawLogPayload } from '../models/log-entry.model';

const DEFAULT_WS_URL = 'ws://localhost:8000/ws/logs';
const MAX_LOG_BUFFER = 2500;
const RECONNECT_INTERVAL_SECONDS = 3;

@Injectable({
  providedIn: 'root'
})
export class LogStreamService {
  // Primary Log State (Newest at the top)
  private readonly _logs = signal<LogEntry[]>([]);
  public readonly logs = this._logs.asReadonly();

  // Connection State
  private readonly _connectionState = signal<ConnectionState>({
    status: 'connecting',
    url: DEFAULT_WS_URL,
    retryCount: 0,
    retryCountdown: RECONNECT_INTERVAL_SECONDS
  });
  public readonly connectionState = this._connectionState.asReadonly();

  // Stream Control
  public readonly isPaused = signal<boolean>(false);
  public readonly isSimulating = signal<boolean>(false);

  // Active Filter
  public readonly filter = signal<LogFilter>({
    search: '',
    level: 'all',
    service: 'all'
  });

  // Filtered Logs
  public readonly filteredLogs = computed(() => {
    const all = this._logs();
    const currentFilter = this.filter();
    const searchLower = currentFilter.search.trim().toLowerCase();

    return all.filter(log => {
      // Level filter
      if (currentFilter.level !== 'all' && log.level !== currentFilter.level) {
        return false;
      }
      // Service filter
      if (currentFilter.service !== 'all' && log.service !== currentFilter.service) {
        return false;
      }
      // Search filter
      if (searchLower) {
        const matchesMessage = log.message.toLowerCase().includes(searchLower);
        const matchesService = log.service.toLowerCase().includes(searchLower);
        const matchesLevel = log.level.toLowerCase().includes(searchLower);
        if (!matchesMessage && !matchesService && !matchesLevel) {
          return false;
        }
      }
      return true;
    });
  });

  // Metrics
  public readonly metrics = computed<LogMetrics>(() => {
    const all = this._logs();
    let info = 0;
    let warn = 0;
    let error = 0;
    const serviceSet = new Set<string>();

    for (const log of all) {
      serviceSet.add(log.service);
      if (log.level === 'error') {
        error++;
      } else if (log.level === 'warn') {
        warn++;
      } else {
        info++;
      }
    }

    return {
      total: all.length,
      info,
      warn,
      error,
      services: Array.from(serviceSet).sort()
    };
  });

  // Internal WebSocket and Timer references
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setInterval> | null = null;
  private simulationInterval: ReturnType<typeof setInterval> | null = null;
  private isExplicitlyClosed = false;

  constructor() {
    this.connect(DEFAULT_WS_URL);
  }

  /**
   * Connect to the WebSocket endpoint
   */
  public connect(url: string = DEFAULT_WS_URL): void {
    this.cleanupSocket();
    this.isExplicitlyClosed = false;

    this.updateConnectionState({
      status: 'connecting',
      url,
      lastError: undefined
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
          lastError: undefined
        });
      };

      this.socket.onmessage = (event: MessageEvent) => {
        this.handleIncomingRawMessage(event.data);
      };

      this.socket.onerror = () => {
        // WebSocket error events don't provide details for security reasons
        this.updateConnectionState({
          lastError: 'WebSocket connection error'
        });
      };

      this.socket.onclose = (event: CloseEvent) => {
        if (this.isExplicitlyClosed) return;

        const isReconnecting = this._connectionState().status !== 'connected';
        this.updateConnectionState({
          status: isReconnecting ? 'reconnecting' : 'disconnected',
          retryCount: this._connectionState().retryCount + 1
        });

        this.scheduleReconnect(url);
      };
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown connection error';
      this.updateConnectionState({
        status: 'disconnected',
        lastError: errorMessage
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
      retryCountdown: 0
    });
  }

  /**
   * Retry connection immediately
   */
  public retryNow(): void {
    this.clearReconnectTimer();
    this.connect(this._connectionState().url);
  }

  /**
   * Change target WebSocket URL
   */
  public setUrl(newUrl: string): void {
    if (newUrl !== this._connectionState().url) {
      this.connect(newUrl);
    }
  }

  /**
   * Toggle stream pause state
   */
  public togglePause(): void {
    this.isPaused.update(val => !val);
  }

  /**
   * Clear all logs in memory
   */
  public clearLogs(): void {
    this._logs.set([]);
  }

  /**
   * Set filter options
   */
  public updateFilter(partial: Partial<LogFilter>): void {
    this.filter.update(current => ({ ...current, ...partial }));
  }

  /**
   * Add a single log entry manually (used by incoming socket or simulation)
   */
  public addLog(entry: LogEntry): void {
    if (this.isPaused()) {
      return;
    }

    this._logs.update(current => {
      const next = [entry, ...current];
      if (next.length > MAX_LOG_BUFFER) {
        return next.slice(0, MAX_LOG_BUFFER);
      }
      return next;
    });
  }

  /**
   * Toggle simulated test logs for local development when backend is offline
   */
  public toggleSimulation(): void {
    if (this.isSimulating()) {
      this.stopSimulation();
    } else {
      this.startSimulation();
    }
  }

  public startSimulation(): void {
    this.isSimulating.set(true);
    if (this.simulationInterval) {
      clearInterval(this.simulationInterval);
    }

    // Emit initial burst of diverse logs
    this.generateMockBurst(6);

    // Stream regular mock logs
    this.simulationInterval = setInterval(() => {
      this.generateMockLog();
    }, 1400);
  }

  public stopSimulation(): void {
    this.isSimulating.set(false);
    if (this.simulationInterval) {
      clearInterval(this.simulationInterval);
      this.simulationInterval = null;
    }
  }

  // Private Helper Methods

  private handleIncomingRawMessage(data: unknown): void {
    try {
      let parsed: RawLogPayload;
      if (typeof data === 'string') {
        parsed = JSON.parse(data);
      } else {
        parsed = data as RawLogPayload;
      }

      const logEntry = this.normalizeLogPayload(parsed);
      this.addLog(logEntry);
    } catch {
      // If payload is plain text or unexpected format, wrap safely
      const rawText = String(data);
      const entry: LogEntry = {
        id: this.generateId(),
        timestamp: new Date().toISOString(),
        displayTime: this.formatDisplayTime(new Date()),
        service: 'system',
        level: 'info',
        message: rawText,
        rawTimestamp: Date.now()
      };
      this.addLog(entry);
    }
  }

  private normalizeLogPayload(payload: RawLogPayload): LogEntry {
    const now = new Date();
    const tsString = payload.timestamp || now.toISOString();
    const dateObj = new Date(tsString);
    const validDate = isNaN(dateObj.getTime()) ? now : dateObj;

    let level: LogLevel = 'info';
    const rawLevel = String(payload.level || 'info').toLowerCase();
    if (rawLevel.includes('err') || rawLevel.includes('fatal') || rawLevel.includes('crit')) {
      level = 'error';
    } else if (rawLevel.includes('warn')) {
      level = 'warn';
    }

    return {
      id: this.generateId(),
      timestamp: tsString,
      displayTime: this.formatDisplayTime(validDate),
      service: (payload.service || 'unknown-service').trim(),
      level,
      message: (payload.message || JSON.stringify(payload)).trim(),
      rawTimestamp: validDate.getTime()
    };
  }

  private formatDisplayTime(date: Date): string {
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    const millis = String(date.getMilliseconds()).padStart(3, '0');
    return `${hours}:${minutes}:${seconds}.${millis}`;
  }

  private scheduleReconnect(url: string): void {
    this.clearReconnectTimer();

    let remainingSeconds = RECONNECT_INTERVAL_SECONDS;
    this.updateConnectionState({
      status: 'reconnecting',
      retryCountdown: remainingSeconds
    });

    this.reconnectTimer = setInterval(() => {
      remainingSeconds--;
      if (remainingSeconds <= 0) {
        this.clearReconnectTimer();
        this.connect(url);
      } else {
        this.updateConnectionState({
          retryCountdown: remainingSeconds
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
    this._connectionState.update(current => ({ ...current, ...partial }));
  }

  private generateId(): string {
    return Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
  }

  // Mock SRE Data Generator
  private mockServices = [
    'auth-service',
    'payment-gw',
    'order-api',
    'k8s-ingress',
    'db-postgres',
    'cache-redis',
    'notification-worker',
    'inventory-svc'
  ];

  private mockTemplates = [
    { level: 'info' as LogLevel, service: 'k8s-ingress', msg: 'GET /api/v1/health HTTP/1.1 200 OK 4.2ms [10.244.0.12]' },
    { level: 'info' as LogLevel, service: 'auth-service', msg: 'JWT token validated for subject user_981248 (tenant=prod-us)' },
    { level: 'info' as LogLevel, service: 'order-api', msg: 'Order #ORD-99411 status changed: PENDING -> PROCESSING' },
    { level: 'warn' as LogLevel, service: 'cache-redis', msg: 'High memory watermark reached: 82.4% allocated (eviction policy: allkeys-lru)' },
    { level: 'info' as LogLevel, service: 'payment-gw', msg: 'Stripe webhook received: charge.succeeded [evt_3N8x7728]' },
    { level: 'warn' as LogLevel, service: 'db-postgres', msg: 'Slow query detected (duration: 842ms): SELECT * FROM orders WHERE status = $1' },
    { level: 'error' as LogLevel, service: 'payment-gw', msg: 'ConnectionTimeoutException: upstream payment vault unreachable after 5000ms' },
    { level: 'error' as LogLevel, service: 'auth-service', msg: 'RateLimitExceeded: IP 198.51.100.44 exceeded 100 req/s threshold' },
    { level: 'info' as LogLevel, service: 'notification-worker', msg: 'Dispatched 42 push notifications via FCM in 18ms' },
    { level: 'warn' as LogLevel, service: 'order-api', msg: 'Inventory reservation retry 2/3 for SKU-88329-XL' },
    { level: 'error' as LogLevel, service: 'db-postgres', msg: 'FATAL: remaining connection slots are reserved for non-replication superuser connections' }
  ];

  private generateMockBurst(count: number): void {
    const now = Date.now();
    for (let i = count; i >= 1; i--) {
      const template = this.mockTemplates[Math.floor(Math.random() * this.mockTemplates.length)];
      const logDate = new Date(now - i * 1000);
      const entry: LogEntry = {
        id: this.generateId(),
        timestamp: logDate.toISOString(),
        displayTime: this.formatDisplayTime(logDate),
        service: template.service,
        level: template.level,
        message: template.msg,
        rawTimestamp: logDate.getTime()
      };
      this.addLog(entry);
    }
  }

  private generateMockLog(): void {
    const template = this.mockTemplates[Math.floor(Math.random() * this.mockTemplates.length)];
    const now = new Date();
    const entry: LogEntry = {
      id: this.generateId(),
      timestamp: now.toISOString(),
      displayTime: this.formatDisplayTime(now),
      service: template.service,
      level: template.level,
      message: template.msg,
      rawTimestamp: now.getTime()
    };
    this.addLog(entry);
  }
}
