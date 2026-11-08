import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, effect, inject, input, output, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { lucideLoaderCircle, lucideTrash2 } from '@ng-icons/lucide';
import { toast } from '@spartan-ng/brain/sonner';
import { HlmAvatarImports } from '@spartan-ng/helm/avatar';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmDialogImports } from '@spartan-ng/helm/dialog';
import { HlmDropdownMenuImports } from '@spartan-ng/helm/dropdown-menu';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { BazeApi } from '../api/baze-api';
import { BazeAppTile } from '../baze/brand';
import type { AppLabel, ShelfApp } from '../api/models';
import { BAZE_ICONS } from './icons';

@Component({
  selector: 'bz-app-card',
  imports: [NgTemplateOutlet, RouterLink, NgIcon, HlmAvatarImports, HlmBadgeImports, HlmButtonImports, HlmDialogImports, HlmDropdownMenuImports, HlmInputImports, BazeAppTile],
  providers: [provideIcons({ ...BAZE_ICONS, lucideLoaderCircle, lucideTrash2 })],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app-card.html',
  host: { class: 'bz-app-card block h-40' },
})
export class AppCard {
  readonly app = input.required<ShelfApp>();

  private readonly api = inject(BazeApi);
  private readonly router = inject(Router);
  private readonly override = signal<ShelfApp | null>(null);
  protected readonly pending = signal<'start' | 'stop' | 'delete' | null>(null);
  protected readonly deleteCode = signal('');
  readonly removed = output<string>();

  constructor() {
    effect(() => {
      this.app();
      this.override.set(null);
    });
  }

  protected shown(): ShelfApp {
    return this.override() ?? this.app();
  }

  protected manage(): void {
    void this.router.navigate(['/apps', this.shown().id]);
  }

  protected start(): void {
    this.power('start');
  }

  protected stop(): void {
    this.power('stop');
  }

  private power(action: 'start' | 'stop'): void {
    const app = this.shown();
    if (!app.runnable || this.pending()) return;
    this.pending.set(action);
    this.api.power(app.id, action).subscribe({
      next: (next) => {
        this.override.set(next);
        this.pending.set(null);
      },
      error: () => {
        this.pending.set(null);
        toast(action === 'start' ? 'The app did not start.' : 'The app did not stop.');
      },
    });
  }

  protected onDeleteCode(event: Event): void {
    this.deleteCode.set((event.target as HTMLInputElement).value);
  }

  protected remove(ctx: { close: () => void }): void {
    const app = this.shown();
    const code = this.deleteCode().trim();
    if (!app.deletable || this.pending() || !code) return;
    this.pending.set('delete');
    this.api.deleteApp(app.id, code).subscribe({
      next: () => {
        this.pending.set(null);
        this.deleteCode.set('');
        ctx.close();
        this.removed.emit(app.id);
      },
      error: (error: unknown) => {
        this.pending.set(null);
        toast(refusal(error, 'The app was not deleted.'));
      },
    });
  }

  protected labels(): AppLabel[] {
    const app = this.shown();
    if (app.labels?.length) return app.labels;
    const labels: AppLabel[] = [];
    if (app.badge) labels.push({ text: app.badge, tone: 'secondary' });
    if (app.statusLabel) {
      labels.push({
        text: app.statusLabel,
        tone: app.status === 'live' ? 'success' : app.status === 'attention' ? 'warning' : app.status === 'building' ? 'secondary' : 'outline',
      });
    }
    return labels;
  }
}

function refusal(error: unknown, fallback: string): string {
  const body = error as { status?: number; error?: { description?: string } };
  if (body?.status === 403 && body.error?.description) return body.error.description;
  return fallback;
}
