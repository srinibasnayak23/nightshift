import {
  Component,
  ElementRef,
  ViewChild,
  effect,
  inject,
  signal
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { LogStreamService } from '../../services/log-stream.service';
import { LogEntry } from '../../models/log-entry.model';

@Component({
  selector: 'app-log-table',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './log-table.component.html',
  styleUrls: ['./log-table.component.css']
})
export class LogTableComponent {
  public readonly streamService = inject(LogStreamService);

  @ViewChild('logContainer') private logContainerRef!: ElementRef<HTMLDivElement>;

  public isUserScrolled = signal<boolean>(false);
  public unreadCount = signal<number>(0);
  public copiedLogId = signal<string | null>(null);
  public expandedLogIds = signal<Set<string>>(new Set());

  private lastKnownTotalCount = 0;

  constructor() {
    // Effect to monitor new incoming logs and update unread count or auto-scroll
    effect(() => {
      const logs = this.streamService.logs();
      const totalCount = logs.length;

      if (totalCount > this.lastKnownTotalCount) {
        const added = totalCount - this.lastKnownTotalCount;
        if (this.isUserScrolled()) {
          this.unreadCount.update(c => c + added);
        } else {
          // Stay at top if user hasn't scrolled down
          this.scrollToTop(false);
        }
      }

      this.lastKnownTotalCount = totalCount;
    });
  }

  public onScroll(): void {
    if (!this.logContainerRef) return;
    const el = this.logContainerRef.nativeElement;
    // If scrolled down by more than 40px, user is looking at older logs
    const isScrolledDown = el.scrollTop > 40;
    this.isUserScrolled.set(isScrolledDown);

    if (!isScrolledDown) {
      this.unreadCount.set(0);
    }
  }

  public scrollToTop(smooth = true): void {
    if (!this.logContainerRef) return;
    const el = this.logContainerRef.nativeElement;
    el.scrollTo({
      top: 0,
      behavior: smooth ? 'smooth' : 'auto'
    });
    this.isUserScrolled.set(false);
    this.unreadCount.set(0);
  }

  public toggleExpand(id: string): void {
    const current = new Set(this.expandedLogIds());
    if (current.has(id)) {
      current.delete(id);
    } else {
      current.add(id);
    }
    this.expandedLogIds.set(current);
  }

  public isExpanded(id: string): boolean {
    return this.expandedLogIds().has(id);
  }

  public copyLog(log: LogEntry, event: Event): void {
    event.stopPropagation();
    const formatted = `[${log.timestamp}] [${log.level.toUpperCase()}] [${log.service}] ${log.message}`;
    navigator.clipboard.writeText(formatted).then(() => {
      this.copiedLogId.set(log.id);
      setTimeout(() => {
        if (this.copiedLogId() === log.id) {
          this.copiedLogId.set(null);
        }
      }, 1500);
    });
  }

  public getServiceColorClass(service: string): string {
    const classes = ['svc-tag-1', 'svc-tag-2', 'svc-tag-3', 'svc-tag-4', 'svc-tag-5', 'svc-tag-6', 'svc-tag-7'];
    let hash = 0;
    for (let i = 0; i < service.length; i++) {
      hash = (hash << 5) - hash + service.charCodeAt(i);
      hash |= 0;
    }
    const idx = Math.abs(hash) % classes.length;
    return classes[idx];
  }
}
