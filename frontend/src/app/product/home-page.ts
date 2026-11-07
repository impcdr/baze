import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { toast } from '@spartan-ng/brain/sonner';
import { startWith, Subject, switchMap } from 'rxjs';
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
  private readonly loads = new Subject<void>();

  protected readonly home = toSignal(this.loads.pipe(startWith(undefined), switchMap(() => this.api.home())));
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

  protected reload(): void {
    this.loads.next();
  }

  private start(prompt: string): void {
    if (!prompt) return;
    void this.router.navigate(['/creator'], { state: { prompt } });
  }
}
