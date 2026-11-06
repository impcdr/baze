import { ChangeDetectionStrategy, Component, ElementRef, Input, inject, signal, viewChild } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  lucideArrowUp,
  lucideCopy,
  lucideEllipsis,
  lucidePencil,
  lucidePlus,
  lucideSquare,
  lucideTrash2,
} from '@ng-icons/lucide';
import { toast } from '@spartan-ng/brain/sonner';
import { HlmAvatarImports } from '@spartan-ng/helm/avatar';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmBubbleImports } from '@spartan-ng/helm/bubble';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmDialogImports, HlmDialog } from '@spartan-ng/helm/dialog';
import { HlmDropdownMenuImports } from '@spartan-ng/helm/dropdown-menu';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { HlmInputGroupImports } from '@spartan-ng/helm/input-group';
import { HlmKbdImports } from '@spartan-ng/helm/kbd';
import { HlmMessageImports } from '@spartan-ng/helm/message';
import { HlmMessageScrollerImports } from '@spartan-ng/helm/message-scroller';
import { HlmSpinnerImports } from '@spartan-ng/helm/spinner';
import { BazeLogo } from '../baze/brand';
import { ChatStore } from './chat-store';

export const STARTER_PROMPTS = [
  'Say this more clearly',
  'Plan a quiet weekend',
  'Explain signals in Angular',
  'Draft a short note',
] as const;

@Component({
  selector: 'app-chat-panel',
  imports: [
    NgIcon,
    BazeLogo,
    HlmButtonImports,
    HlmAvatarImports,
    HlmBadgeImports,
    HlmMessageImports,
    HlmBubbleImports,
    HlmMessageScrollerImports,
    HlmInputGroupImports,
    HlmDropdownMenuImports,
    HlmDialogImports,
    HlmKbdImports,
    HlmSpinnerImports,
    HlmInputImports,
  ],
  providers: [
    provideIcons({
      lucideArrowUp,
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
  host: {
    '[class]': 'docked ? "block" : "flex min-h-0 flex-1 flex-col"',
  },
})
export class ChatPanel {
  @Input() docked = true;
  protected readonly store = inject(ChatStore);
  protected readonly prompts = STARTER_PROMPTS;
  protected readonly renameDraft = signal('');
  protected readonly draft = signal('');
  private readonly composer = viewChild<ElementRef<HTMLTextAreaElement>>('composer');

  focusComposer(): void {
    this.composer()?.nativeElement.focus({ preventScroll: true });
  }

  protected startNewChat(): void {
    this.store.newChat();
    this.focusComposer();
  }

  protected selectChat(id: string): void {
    this.store.select(id);
    this.focusComposer();
  }

  protected ask(prompt: string): void {
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

  protected async copy(text: string): Promise<void> {
    await navigator.clipboard.writeText(text);
    toast.success('Copied');
  }

  protected onRenameInput(event: Event): void {
    this.renameDraft.set((event.target as HTMLInputElement).value);
  }

  private sendDraft(): void {
    const field = this.composer()?.nativeElement;
    const text = field?.value ?? this.draft();
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
}
