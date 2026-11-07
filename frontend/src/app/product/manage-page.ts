import { ChangeDetectionStrategy, Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { lucideArrowLeft, lucideArrowUp, lucideLoaderCircle, lucideTrash2 } from '@ng-icons/lucide';
import { toast } from '@spartan-ng/brain/sonner';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmDialogImports } from '@spartan-ng/helm/dialog';
import { HlmSwitchImports } from '@spartan-ng/helm/switch';
import { distinctUntilChanged, map, switchMap, takeWhile, timer } from 'rxjs';
import { BazeApi } from '../api/baze-api';
import type { AppManage, AppTurn } from '../api/models';
import { BazeAppTile } from '../baze/brand';
import { BAZE_ICONS } from './icons';

@Component({
  selector: 'bz-manage',
  imports: [RouterLink, NgIcon, HlmBadgeImports, HlmButtonImports, HlmDialogImports, HlmSwitchImports, BazeAppTile],
  providers: [provideIcons({ ...BAZE_ICONS, lucideArrowLeft, lucideArrowUp, lucideLoaderCircle, lucideTrash2 })],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './manage-page.html',
  host: { class: 'flex min-h-0 flex-1 flex-col overflow-hidden pb-6' },
})
export class ManagePage {
  private readonly api = inject(BazeApi);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly app = signal<AppManage | null>(null);
  protected readonly draft = signal('');
  protected readonly sending = signal(false);
  protected readonly powering = signal(false);
  protected readonly running = signal(false);
  private readonly thread = viewChild<ElementRef<HTMLElement>>('thread');
  private asked = false;

  constructor() {
    this.route.paramMap
      .pipe(
        map((params) => params.get('id') ?? ''),
        distinctUntilChanged(),
        switchMap((id) => {
          this.asked = false;
          return timer(0, 1000).pipe(
            switchMap(() => this.api.manage(id)),
            takeWhile((page) => page.status === 'building', true),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((page) => {
        this.app.set(page);
        this.running.set(page.status === 'live');
        this.scroll();
        if (page.boxReady && page.status === 'building' && !this.asked) {
          this.asked = true;
          this.api.build(page.id).subscribe({
            error: () => {
              this.asked = false;
            },
          });
        }
      });
  }

  protected when(value: number | null, empty = 'Not run yet'): string {
    if (!value) return empty;
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(value);
  }

  protected onDraft(event: Event): void {
    this.draft.set((event.target as HTMLTextAreaElement).value);
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  protected toggle(on: boolean): void {
    const page = this.app();
    if (!page || !page.runnable || this.powering() || on === this.running()) return;
    const previous = this.running();
    this.running.set(on);
    this.powering.set(true);
    this.api.power(page.id, on ? 'start' : 'stop').subscribe({
      next: () => {
        this.api.manage(page.id).subscribe({
          next: (fresh) => {
            this.app.set(fresh);
            this.running.set(fresh.status === 'live');
            this.powering.set(false);
          },
          error: () => this.powering.set(false),
        });
      },
      error: () => {
        this.running.set(previous);
        this.powering.set(false);
        toast(on ? 'The app did not start.' : 'The app did not stop.');
      },
    });
  }

  protected remove(): void {
    const page = this.app();
    if (!page?.deletable || this.powering()) return;
    this.powering.set(true);
    this.api.deleteApp(page.id).subscribe({
      next: () => {
        void this.router.navigate(['/apps']);
      },
      error: () => {
        this.powering.set(false);
        toast('The app was not deleted.');
      },
    });
  }

  protected send(): void {
    const page = this.app();
    const content = this.draft().trim();
    if (!page || page.status !== 'live' || !content || this.sending()) return;
    const mine: AppTurn = { id: `local-${Date.now()}`, role: 'user', content, createdAt: Date.now() };
    this.app.set({ ...page, messages: [...page.messages, mine] });
    this.draft.set('');
    this.sending.set(true);
    this.scroll();
    this.api.prompt(page.id, content).subscribe({
      next: (result) => {
        const current = this.app();
        if (!current) return;
        const reply: AppTurn = {
          id: `reply-${Date.now()}`,
          role: 'assistant',
          content: result.reply,
          createdAt: Date.now(),
        };
        this.app.set({ ...current, messages: [...current.messages, reply] });
        this.sending.set(false);
        this.scroll();
      },
      error: () => {
        this.sending.set(false);
        toast('The app did not answer.');
      },
    });
  }

  private scroll(): void {
    queueMicrotask(() => {
      const node = this.thread()?.nativeElement;
      if (node) node.scrollTop = node.scrollHeight;
    });
  }
}
