import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { lucideArrowLeft, lucideArrowUp, lucideLoaderCircle, lucideMinus, lucidePaperclip, lucideShieldAlert, lucideTrash2, lucideX } from '@ng-icons/lucide';
import { toast } from '@spartan-ng/brain/sonner';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmCheckboxImports } from '@spartan-ng/helm/checkbox';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { HlmDialogImports } from '@spartan-ng/helm/dialog';
import { HlmSwitchImports } from '@spartan-ng/helm/switch';
import { HlmTooltipImports } from '@spartan-ng/helm/tooltip';
import { catchError, distinctUntilChanged, EMPTY, map, of, Subscription, switchMap, takeWhile, timer } from 'rxjs';
import { BazeApi } from '../api/baze-api';
import type { AppManage, AppTurn, ChartEntry } from '../api/models';
import { BazeAppTile } from '../baze/brand';
import { BAZE_ICONS } from './icons';

@Component({
  selector: 'bz-manage',
  imports: [RouterLink, NgIcon, HlmBadgeImports, HlmButtonImports, HlmCheckboxImports, HlmDialogImports, HlmInputImports, HlmSwitchImports, HlmTooltipImports, BazeAppTile],
  providers: [provideIcons({ ...BAZE_ICONS, lucideArrowLeft, lucideArrowUp, lucideLoaderCircle, lucideMinus, lucidePaperclip, lucideShieldAlert, lucideTrash2, lucideX })],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './manage-page.html',
  host: { class: 'flex min-h-0 flex-1 flex-col overflow-hidden pb-6' },
})
export class ManagePage {
  private readonly api = inject(BazeApi);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly app = signal<AppManage | null>(null);
  private readonly now = signal(Date.now());
  protected readonly draft = signal('');
  protected readonly files = signal<File[]>([]);
  protected readonly sending = signal(false);
  protected readonly picked = signal<string[]>([]);
  private appliedSites = '';
  protected readonly powering = signal(false);
  protected readonly sharing = signal(false);
  protected readonly persisting = signal(false);
  protected readonly persistCode = signal('');
  protected readonly deleteCode = signal('');
  protected readonly running = signal(false);
  protected readonly chosen = signal<ChartEntry | null>(null);
  protected readonly made = signal('');
  private readonly thread = viewChild<ElementRef<HTMLElement>>('thread');
  private asked = false;
  private pulse: Subscription | null = null;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.pulse?.unsubscribe());
    timer(0, 1000)
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.now.set(Date.now()));
    this.route.paramMap
      .pipe(
        map((params) => params.get('id') ?? ''),
        distinctUntilChanged(),
        switchMap((id) => {
          this.asked = false;
          return timer(0, 1000).pipe(
            switchMap(() => this.api.manage(id)),
            takeWhile((page) => page.status === 'building' || !!page.working || this.spinning(page), true),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((page) => {
        this.app.set(page);
        this.rememberSites(page);
        this.running.set(page.status === 'live');
        this.scroll();
        if (page.canPrompt && page.boxReady && page.status === 'building' && !this.asked) {
          this.asked = true;
          this.api.build(page.id).subscribe({
            error: () => {
              this.asked = false;
            },
          });
        }
      });
  }

  protected timeLeft(page: AppManage): string | null {
    if (page.demo || !page.expiresAt) return null;
    const seconds = Math.max(0, Math.ceil((page.expiresAt - this.now()) / 1000));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remain = seconds % 60;
    const clock = `${minutes}:${String(remain).padStart(2, '0')}`;
    return hours > 0 ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remain).padStart(2, '0')}` : clock;
  }

  protected when(value: number | null, empty = 'Not run yet'): string {
    if (!value) return empty;
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(value);
  }

  protected onDraft(event: Event): void {
    this.draft.set((event.target as HTMLTextAreaElement).value);
  }

  protected onFiles(event: Event): void {
    const input = event.target as HTMLInputElement;
    const picked = Array.from(input.files ?? []);
    input.value = '';
    if (picked.length === 0) return;
    this.files.update((current) => [...current, ...picked].slice(0, 4));
  }

  protected dropFile(file: File): void {
    this.files.update((current) => current.filter((item) => item !== file));
  }

  protected entryLabel(entry: ChartEntry): string {
    if (this.deployed(entry)) return 'Deployed';
    if (entry.kind === 'decision') return 'Decision';
    if (entry.kind === 'created') return 'Created';
    if (entry.kind === 'containment') return 'Containment';
    return 'Change';
  }

  protected entryTone(entry: ChartEntry): 'success' | 'warning' | 'outline' {
    if (this.deployed(entry)) return 'success';
    if (entry.kind === 'containment') return 'warning';
    return 'outline';
  }

  protected shortRecord(entry: ChartEntry): string {
    if (this.deployed(entry)) return 'Approved';
    let text = entry.summary.replace(/\s+/g, ' ').trim();
    if (entry.kind === 'created') text = text.replace(/\.?\s*It was created\.?$/i, '').trim();
    if (text.length <= 72) return text;
    const cut = text.slice(0, 72);
    const space = cut.lastIndexOf(' ');
    return `${(space > 40 ? cut.slice(0, space) : cut).trimEnd()}…`;
  }

  private deployed(entry: ChartEntry): boolean {
    return entry.summary.trim().toLowerCase() === 'supervisor approved, app deployed.';
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

  protected onDeleteCode(event: Event): void {
    this.deleteCode.set((event.target as HTMLInputElement).value);
  }

  protected remove(ctx: { close: () => void }): void {
    const page = this.app();
    const code = this.deleteCode().trim();
    if (!page?.deletable || this.powering() || !code) return;
    this.powering.set(true);
    this.api.deleteApp(page.id, code).subscribe({
      next: () => {
        this.powering.set(false);
        this.deleteCode.set('');
        ctx.close();
        void this.router.navigate(['/apps']);
      },
      error: (error: unknown) => {
        this.powering.set(false);
        toast(refusal(error, 'The app was not deleted.'));
      },
    });
  }

  protected share(email: string, on: boolean): void {
    const page = this.app();
    const row = page?.shares.find((person) => person.email === email);
    if (!page?.canPrompt || !row || row.owner || row.shared === on || this.sharing()) return;
    this.sharing.set(true);
    this.api.share(page.id, email, on).subscribe({
      next: (fresh) => {
        this.app.update((current) => (current ? { ...current, shares: fresh.shares } : current));
        this.sharing.set(false);
      },
      error: () => {
        this.sharing.set(false);
        toast('The app was not shared.');
      },
    });
  }

  protected onPersistCode(event: Event): void {
    this.persistCode.set((event.target as HTMLInputElement).value);
  }

  protected persist(ctx: { close: () => void }): void {
    const page = this.app();
    const code = this.persistCode().trim();
    if (!page?.canPrompt || page.demo || !code || this.persisting()) return;
    this.persisting.set(true);
    this.api.persist(page.id, code).subscribe({
      next: () => {
        this.persisting.set(false);
        this.persistCode.set('');
        ctx.close();
        this.api.manage(page.id).subscribe({
          next: (fresh) => {
            this.app.set(fresh);
            this.running.set(fresh.status === 'live');
          },
        });
      },
      error: (error: unknown) => {
        this.persisting.set(false);
        toast(refusal(error, 'That code did not persist the app.'));
      },
    });
  }

  protected open(page: AppManage): boolean {
    return page.status === 'live' || page.status === 'attention';
  }

  protected held(page: AppManage): boolean {
    return this.sending() || !!page.working;
  }

  protected needsDecision(page: AppManage): boolean {
    return page.sites.length > 0;
  }

  protected statusText(page: AppManage): string {
    if (this.needsDecision(page)) return 'Needs a decision';
    if (page.status === 'live') return 'Live';
    if (page.status === 'building') return 'Being made';
    if (page.status === 'error') return 'Didn’t start';
    if (page.status === 'attention') return page.statusLabel && page.statusLabel !== 'Needs a decision' ? page.statusLabel : 'Not deployed';
    if (page.status === 'closed') return 'Closed';
    return 'Off';
  }

  protected siteRows(page: AppManage): { host: string; suggested: boolean }[] {
    if (page.sites.length > 0) return page.sites;
    return [
      ...page.allowed.map((host) => ({ host, suggested: true })),
      ...page.closed.map((host) => ({ host, suggested: false })),
    ];
  }

  protected isPicked(host: string): boolean {
    return this.picked().includes(host);
  }

  protected toggleSite(host: string, event: Event): void {
    const on = (event.target as HTMLInputElement).checked;
    this.picked.update((current) => (on ? [...current.filter((item) => item !== host), host] : current.filter((item) => item !== host)));
  }

  protected deciding(page: AppManage, message: AppTurn): boolean {
    if (page.status !== 'attention' || message.role !== 'supervisor') return false;
    if (!page.boxPrompt && page.sites.length === 0) return false;
    const last = [...page.messages].reverse().find((item) => item.role === 'supervisor');
    return last?.id === message.id;
  }

  protected answerBox(allow: boolean): void {
    const page = this.app();
    if (!page || this.sending()) return;
    this.sending.set(true);
    this.watch(page.id);
    this.api.allowBox(page.id, allow).subscribe({
      next: () => {
        this.api.manage(page.id).subscribe({
          next: (fresh) => {
            this.app.set(fresh);
            this.running.set(fresh.status === 'live');
            this.sending.set(false);
            this.scroll();
            if (!this.stillGoing(fresh)) this.pulse?.unsubscribe();
          },
          error: () => {
            this.pulse?.unsubscribe();
            this.sending.set(false);
            toast('The app did not answer.');
          },
        });
      },
      error: () => {
        this.sending.set(false);
        toast('The decision was not saved.');
      },
    });
  }

  protected prepareDecision(): void {
    const page = this.app();
    if (!page) return;
    this.picked.set(page.sites.filter((site) => site.suggested).map((site) => site.host));
  }

  protected approve(): void {
    const page = this.app();
    const hosts = this.picked();
    if (!page || this.sending()) return;
    const messages = page.messages.map((message) =>
      message.role === 'supervisor' && message.id === [...page.messages].reverse().find((item) => item.role === 'supervisor')?.id
        ? { ...message, decided: true }
        : message,
    );
    this.app.set({ ...page, messages, sites: [] });
    this.sending.set(true);
    this.scroll();
    this.watch(page.id);
    this.api.approve(page.id, hosts).subscribe({
      next: () => {
        this.api.manage(page.id).subscribe({
          next: (fresh) => {
            this.app.set(fresh);
            this.rememberSites(fresh);
            this.running.set(fresh.status === 'live');
            this.sending.set(false);
            this.scroll();
            if (!this.stillGoing(fresh)) this.pulse?.unsubscribe();
          },
          error: () => {
            this.pulse?.unsubscribe();
            this.sending.set(false);
            toast('The app did not answer.');
          },
        });
      },
      error: (error: unknown) => {
        this.app.set(page);
        this.sending.set(false);
        if (!this.spinning(page)) this.pulse?.unsubscribe();
        toast(refusal(error, 'The app did not answer.'));
      },
    });
  }

  private rememberSites(page: AppManage): void {
    const rows = this.siteRows(page);
    const key = rows.map((site) => `${site.host}:${site.suggested ? 1 : 0}`).join('|');
    if (key === this.appliedSites) return;
    this.appliedSites = key;
    this.picked.set(rows.filter((site) => site.suggested).map((site) => site.host));
  }

  protected sendToSupervisor(): void {
    const page = this.app();
    const content = this.draft().trim();
    if (!page || !this.open(page) || this.sending() || page.working || !content) return;
    const mine: AppTurn = { id: `local-${Date.now()}`, role: 'user', content, createdAt: Date.now() };
    this.app.set({ ...page, messages: [...page.messages, mine] });
    this.draft.set('');
    this.sending.set(true);
    this.scroll();
    this.api.prompt(page.id, content, [], 'supervisor').subscribe({
      next: () => {
        this.api.manage(page.id).subscribe({
          next: (fresh) => {
            this.app.set(fresh);
            this.rememberSites(fresh);
            this.running.set(fresh.status === 'live');
            this.sending.set(false);
            this.scroll();
          },
          error: (error: unknown) => {
            this.sending.set(false);
            toast(refusal(error, 'The supervisor did not answer.'));
          },
        });
      },
      error: (error: unknown) => {
        this.app.set(page);
        this.draft.set(content);
        this.sending.set(false);
        toast(refusal(error, 'The supervisor did not answer.'));
      },
    });
  }

  protected send(): void {
    const page = this.app();
    const content = this.draft().trim();
    const pending = this.files();
    if (!page || !this.open(page) || this.sending() || page.working || (!content && pending.length === 0)) return;
    const spoken = content || 'Use the attached files.';
    const shown = pending.length === 0 ? spoken : `${spoken}\n${pending.map((file) => file.name).join('\n')}`;
    const mine: AppTurn = { id: `local-${Date.now()}`, role: 'user', content: shown, createdAt: Date.now() };
    this.app.set({ ...page, messages: [...page.messages, mine] });
    this.draft.set('');
    this.files.set([]);
    this.sending.set(true);
    this.scroll();
    this.watch(page.id, mine.id);
    const upload$ = pending.length ? this.api.upload(page.id, pending) : of({ files: [] as { name: string }[] });
    upload$.pipe(switchMap((saved) => this.api.prompt(page.id, spoken, saved.files.map((file) => file.name)))).subscribe({
      next: () => {
        this.api.manage(page.id).subscribe({
          next: (fresh) => {
            this.app.set(fresh);
            this.running.set(fresh.status === 'live');
            this.sending.set(false);
            this.scroll();
            if (!this.stillGoing(fresh)) this.pulse?.unsubscribe();
          },
          error: () => {
            this.pulse?.unsubscribe();
            this.sending.set(false);
            toast('The app did not answer.');
          },
        });
      },
      error: (error: unknown) => {
        this.sending.set(false);
        this.api.manage(page.id).subscribe({
          next: (fresh) => {
            const kept = fresh.messages.some((message) => message.role === 'user' && message.content === shown);
            this.app.set(fresh);
            if (!kept) {
              this.draft.set(content);
              this.files.set(pending);
            }
            if (!this.spinning(fresh)) this.pulse?.unsubscribe();
          },
          error: () => {
            this.app.update((current) =>
              current ? { ...current, messages: current.messages.filter((message) => message.id !== mine.id) } : current,
            );
            this.draft.set(content);
            this.files.set(pending);
          },
        });
        toast(refusal(error, 'The app did not answer.'));
      },
    });
  }

  private watch(id: string, pendingId = ''): void {
    this.pulse?.unsubscribe();
    this.pulse = timer(500, 1000)
      .pipe(
        switchMap(() => this.api.manage(id).pipe(catchError(() => EMPTY))),
        takeWhile((fresh) => this.sending() || this.stillGoing(fresh), true),
      )
      .subscribe((fresh) => {
        const pending = pendingId ? this.app()?.messages.find((message) => message.id === pendingId) : undefined;
        this.app.set(pending ? this.withPending(fresh, pending) : fresh);
        this.running.set(fresh.status === 'live');
        this.scroll();
      });
  }

  private stillGoing(page: AppManage): boolean {
    return !!page.working || this.spinning(page);
  }

  private spinning(page: AppManage): boolean {
    return page.messages.some((message) => message.role === 'progress' && message.state === 'active');
  }

  private withPending(fresh: AppManage, pending: AppTurn): AppManage {
    const landed = fresh.messages.some(
      (message) => message.role === 'user' && message.content === pending.content && message.createdAt >= pending.createdAt - 15000,
    );
    if (landed) return fresh;
    return { ...fresh, messages: [...fresh.messages, pending] };
  }

  private scroll(): void {
    queueMicrotask(() => {
      const node = this.thread()?.nativeElement;
      if (node) node.scrollTop = node.scrollHeight;
    });
  }
}

function refusal(error: unknown, fallback: string): string {
  const body = error as { status?: number; error?: { description?: string } };
  if ((body?.status === 429 || body?.status === 403) && body.error?.description) return body.error.description;
  return fallback;
}
