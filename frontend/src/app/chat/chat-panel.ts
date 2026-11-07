import {
  afterEveryRender,
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  lucideArrowUp,
  lucideCheck,
  lucideChevronDown,
  lucideCopy,
  lucideEllipsis,
  lucidePencil,
  lucidePlus,
  lucideSquare,
  lucideTrash2,
} from '@ng-icons/lucide';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmDialog, HlmDialogImports } from '@spartan-ng/helm/dialog';
import { HlmDropdownMenuImports } from '@spartan-ng/helm/dropdown-menu';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { ChatStore } from './chat-store';

export const STARTER_PROMPTS = [
  'Say this more clearly',
  'Plan a quiet weekend',
  'Explain signals in Angular',
  'Draft a short note',
] as const;

@Component({
  selector: 'app-chat-panel',
  imports: [NgIcon, HlmButtonImports, HlmDropdownMenuImports, HlmDialogImports, HlmInputImports],
  providers: [
    provideIcons({
      lucideArrowUp,
      lucideCheck,
      lucideChevronDown,
      lucideCopy,
      lucideEllipsis,
      lucidePencil,
      lucidePlus,
      lucideSquare,
      lucideTrash2,
    }),
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './chat-panel.html',
  host: { class: 'flex min-h-0 flex-1 flex-col' },
})
export class ChatPanel {
  protected readonly store = inject(ChatStore);
  protected readonly prompts = STARTER_PROMPTS;
  protected readonly renameDraft = signal('');
  protected readonly draft = signal('');
  protected readonly copiedId = signal<string | null>(null);
  /** Keep the latest line in view until the reader scrolls up. */
  private readonly follow = signal(true);
  private readonly thread = viewChild<ElementRef<HTMLElement>>('thread');
  private readonly composer = viewChild<ElementRef<HTMLTextAreaElement>>('composer');
  private scrollKey = '';
  private copyTimer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    inject(DestroyRef).onDestroy(() => {
      if (this.copyTimer) clearTimeout(this.copyTimer);
    });

    afterEveryRender({
      mixedReadWrite: () => {
        const el = this.thread()?.nativeElement;
        if (!el || !this.follow()) return;
        const key = this.store
          .messages()
          .map((message) => `${message.id}:${message.content.length}`)
          .join('|');
        if (key === this.scrollKey) return;
        this.scrollKey = key;
        this.pin(el);
      },
    });
  }

  focusComposer(): void {
    this.composer()?.nativeElement.focus({ preventScroll: true });
  }

  protected showHistory(): boolean {
    return this.store.conversations().length > 1 || (this.store.conversations().length > 0 && !this.store.active());
  }

  protected startNewChat(): void {
    this.store.newChat();
    this.focusComposer();
  }

  protected selectChat(id: string): void {
    this.follow.set(true);
    this.scrollKey = '';
    this.store.select(id);
    this.focusComposer();
  }

  protected ask(prompt: string): void {
    this.follow.set(true);
    this.scrollKey = '';
    this.store.send(prompt);
    this.clearComposer();
  }

  protected onSubmit(event: Event): void {
    event.preventDefault();
    this.sendDraft();
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendDraft();
    }
  }

  protected onDraft(event: Event): void {
    const field = event.target as HTMLTextAreaElement;
    this.draft.set(field.value);
    field.style.height = 'auto';
    field.style.height = `${Math.min(field.scrollHeight, 160)}px`;
  }

  protected onThreadScroll(event: Event): void {
    const el = event.target as HTMLElement;
    if (el.dataset['pinning'] === '1') return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    this.follow.set(distance < 80);
  }

  protected deleteActive(): void {
    const id = this.store.activeId();
    if (id) this.store.remove(id);
  }

  protected beginRename(): void {
    this.renameDraft.set(this.store.active()?.title ?? '');
  }

  protected saveRename(dialog: HlmDialog): void {
    const id = this.store.activeId();
    if (!id) return;
    this.store.rename(id, this.renameDraft());
    dialog.close();
  }

  protected async copy(id: string, text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      return;
    }
    this.copiedId.set(id);
    if (this.copyTimer) clearTimeout(this.copyTimer);
    this.copyTimer = setTimeout(() => this.copiedId.set(null), 1400);
  }

  protected onRenameInput(event: Event): void {
    this.renameDraft.set((event.target as HTMLInputElement).value);
  }

  private sendDraft(): void {
    const field = this.composer()?.nativeElement;
    const text = field?.value ?? this.draft();
    this.follow.set(true);
    this.scrollKey = '';
    this.store.send(text);
    this.clearComposer();
  }

  private clearComposer(): void {
    this.draft.set('');
    const field = this.composer()?.nativeElement;
    if (!field) return;
    field.value = '';
    field.style.height = 'auto';
  }

  private pin(el: HTMLElement): void {
    const apply = () => {
      el.dataset['pinning'] = '1';
      el.scrollTop = el.scrollHeight;
      delete el.dataset['pinning'];
    };
    apply();
    requestAnimationFrame(apply);
  }
}
