import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { BazeApi } from '../api/baze-api';
import { AppCard } from './app-card';
import { BAZE_ICONS } from './icons';

@Component({
  selector: 'bz-home',
  imports: [RouterLink, NgIcon, HlmButtonImports, AppCard],
  providers: [provideIcons(BAZE_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './home-page.html',
  host: { class: 'block min-h-0 flex-1 overflow-y-auto pb-8' },
})
export class HomePage {
  private readonly api = inject(BazeApi);
  private readonly router = inject(Router);
  private readonly typed = signal<string | null>(null);

  protected readonly home = toSignal(this.api.home());
  protected readonly prompt = computed(() => this.typed() ?? this.home()?.prompt ?? '');
  protected readonly sending = signal(false);

  protected type(value: string): void {
    this.typed.set(value);
  }

  protected useSuggestion(prompt: string): void {
    this.typed.set(prompt);
  }

  protected make(): void {
    this.start(this.prompt().trim());
  }

  private start(prompt: string): void {
    if (!prompt || this.sending()) return;
    this.sending.set(true);
    this.api.createDraft(prompt).subscribe((draft) => {
      void this.router.navigate(['/make', draft.id]);
    });
  }
}
