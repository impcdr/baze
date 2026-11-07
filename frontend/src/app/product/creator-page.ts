import { afterNextRender, ChangeDetectionStrategy, Component, DestroyRef, ElementRef, inject, Injector, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { lucideArrowUp, lucideLoaderCircle } from '@ng-icons/lucide';
import { toast } from '@spartan-ng/brain/sonner';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { switchMap, takeWhile, timer } from 'rxjs';
import { BazeApi } from '../api/baze-api';
import type { AppSketch, AppStep, AppTurn } from '../api/models';
import { BazeAppTile, BazeEmptyShelf } from '../baze/brand';
import { BAZE_ICONS } from './icons';

@Component({
  selector: 'bz-creator',
  imports: [NgIcon, HlmButtonImports, BazeEmptyShelf, BazeAppTile],
  providers: [provideIcons({ ...BAZE_ICONS, lucideArrowUp, lucideLoaderCircle })],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './creator-page.html',
  host: { class: 'flex min-h-0 flex-1 flex-col overflow-hidden pb-6' },
})
export class CreatorPage {
  private readonly api = inject(BazeApi);
  private readonly router = inject(Router);
  private readonly destroy = inject(DestroyRef);
  private readonly injector = inject(Injector);

  protected readonly messages = signal<AppTurn[]>([]);
  protected readonly steps = signal<AppStep[]>([]);
  protected readonly sketch = signal<AppSketch>({ name: '', summary: '', icon: '', color: '' });
  protected readonly draft = signal('');
  protected readonly sending = signal(false);
  protected readonly making = signal(false);
  protected readonly settled = signal(false);
  /** Kept mounted after the first empty visit so the shelf can fold away instead of popping. */
  protected readonly shelfOn = signal(false);
  protected readonly take = signal(0);
  private epoch = 0;
  private readonly thread = viewChild<ElementRef<HTMLElement>>('thread');
  private readonly composer = viewChild<ElementRef<HTMLTextAreaElement>>('composer');

  constructor() {
    const prompt = history.state?.prompt;
    const epoch = this.epoch;
    this.api.creator().subscribe({
      next: (thread) => {
        if (epoch !== this.epoch) return;
        this.messages.set(thread.messages);
        this.sketch.set(thread.sketch);
        if (typeof prompt === 'string' && prompt.trim() && thread.messages.length === 0) {
          history.replaceState({}, '');
          this.ask(prompt.trim());
        }
        this.shelfOn.set(this.messages().length === 0 && this.steps().length === 0);
        this.settled.set(true);
        this.focusComposer();
        this.scroll();
      },
      error: () => {
        if (epoch !== this.epoch) return;
        this.shelfOn.set(true);
        this.settled.set(true);
        this.focusComposer();
      },
    });
  }

  protected sketchIcon(): string {
    return this.sketch().icon || 'lucidePackage';
  }

  protected sketchColor(): string {
    const chosen = this.sketch().color;
    if (chosen) return chosen;
    return this.sketch().icon ? '#1a5ce6' : '#b7c2d6';
  }

  protected chatting(): boolean {
    return this.messages().length > 0 || this.steps().length > 0 || this.sending() || this.making();
  }

  protected ready(): boolean {
    return this.messages().some((message) => message.role === 'user');
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

  protected send(): void {
    const content = this.draft().trim();
    if (!content || this.sending() || this.making()) return;
    this.draft.set('');
    this.ask(content);
  }

  protected restart(): void {
    if (this.making() || this.sending()) return;
    this.epoch += 1;
    this.messages.set([]);
    this.steps.set([]);
    this.sketch.set({ name: '', summary: '', icon: '', color: '' });
    this.draft.set('');
    this.sending.set(false);
    this.shelfOn.set(true);
    this.take.update((value) => value + 1);
    this.focusComposer();
    this.api.resetCreator().subscribe({
      error: () => toast('Could not start again.'),
    });
  }

  protected make(): void {
    if (!this.ready() || this.sending() || this.making()) return;
    this.making.set(true);
    this.api.makeCreator().subscribe({
      next: (made) => {
        this.steps.set(made.steps);
        this.scroll();
        this.watch(made.id);
      },
      error: () => {
        this.making.set(false);
        toast('The app did not start.');
      },
    });
  }

  private ask(content: string): void {
    const epoch = this.epoch;
    const mine: AppTurn = { id: `local-${Date.now()}`, role: 'user', content, createdAt: Date.now() };
    this.messages.update((turns) => [...turns, mine]);
    this.sending.set(true);
    this.scroll();
    this.api.creatorMessage(content).subscribe({
      next: (thread) => {
        if (epoch !== this.epoch) return;
        this.messages.set(thread.messages);
        this.sketch.set(thread.sketch);
        this.sending.set(false);
        this.scroll();
      },
      error: () => {
        if (epoch !== this.epoch) return;
        this.messages.update((turns) => turns.filter((turn) => turn.id !== mine.id));
        this.sending.set(false);
        toast('The model did not answer.');
      },
    });
  }

  private watch(id: string): void {
    timer(0, 1000)
      .pipe(
        switchMap(() => this.api.manage(id)),
        takeWhile((page) => !page.boxReady && page.status !== 'error', true),
        takeUntilDestroyed(this.destroy),
      )
      .subscribe((page) => {
        if (page.steps.length) this.steps.set(page.steps);
        this.scroll();
        if (page.boxReady) {
          void this.router.navigate(['/apps', id]);
          return;
        }
        if (page.status === 'error') {
          this.making.set(false);
          toast(page.statusError || 'The container did not start.');
        }
      });
  }

  private focusComposer(): void {
    afterNextRender(() => this.composer()?.nativeElement.focus(), { injector: this.injector });
  }

  private scroll(): void {
    queueMicrotask(() => {
      const node = this.thread()?.nativeElement;
      if (node) node.scrollTop = node.scrollHeight;
    });
  }
}
