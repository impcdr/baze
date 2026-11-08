import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { map, switchMap, takeWhile, timer } from 'rxjs';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { BazeApi } from '../api/baze-api';
import type { ShelfCheck } from '../api/models';

@Component({
  selector: 'bz-quarantine',
  imports: [RouterLink, HlmBadgeImports],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './quarantine-page.html',
  host: { class: 'block min-h-0 flex-1 overflow-y-auto pb-8' },
})
export class QuarantinePage {
  private readonly api = inject(BazeApi);

  protected readonly checks = toSignal(
    timer(0, 1000).pipe(
      switchMap(() => this.api.apps()),
      map((page) => page.checks),
      takeWhile((checks) => checks.some((check) => check.verdict === 'pending'), true),
      takeUntilDestroyed(),
    ),
  );

  protected verdictLabel(verdict: ShelfCheck['verdict']): string {
    if (verdict === 'clear') return 'Clear';
    if (verdict === 'suspicious') return 'Suspicious';
    return 'Pending';
  }

  protected verdictTone(verdict: ShelfCheck['verdict']): 'success' | 'warning' | 'outline' {
    if (verdict === 'clear') return 'success';
    if (verdict === 'suspicious') return 'warning';
    return 'outline';
  }
}
