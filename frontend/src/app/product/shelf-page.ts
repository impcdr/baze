import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { switchMap } from 'rxjs';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmEmptyImports } from '@spartan-ng/helm/empty';
import { BazeApi } from '../api/baze-api';
import type { ShelfPayload } from '../api/models';
import { AppCard } from './app-card';
import { BAZE_ICONS } from './icons';

@Component({
  selector: 'bz-shelf',
  imports: [NgIcon, RouterLink, HlmBadgeImports, HlmButtonImports, HlmEmptyImports, AppCard],
  providers: [provideIcons(BAZE_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './shelf-page.html',
  host: { class: 'block min-h-0 flex-1 overflow-y-auto pb-8' },
})
export class ShelfPage {
  private readonly api = inject(BazeApi);
  private readonly router = inject(Router);

  protected readonly status = signal('all');
  protected readonly shelf = signal<ShelfPayload | null>(null);

  constructor() {
    toObservable(this.status)
      .pipe(
        switchMap((status) => this.api.apps(status)),
        takeUntilDestroyed(),
      )
      .subscribe((page) => this.shelf.set(page));
  }

  protected choose(id: string): void {
    this.status.set(id);
  }

  protected make(): void {
    void this.router.navigate(['/creator']);
  }

  protected reload(): void {
    this.api.apps(this.status()).subscribe((page) => this.shelf.set(page));
  }
}
