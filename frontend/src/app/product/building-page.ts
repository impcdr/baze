import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { catchError, map, of, switchMap } from 'rxjs';
import { HlmAlertImports } from '@spartan-ng/helm/alert';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmProgressImports } from '@spartan-ng/helm/progress';
import { BazeShelfLoader } from '../baze/brand';
import { BazeApi } from '../api/baze-api';
import type { Draft } from '../api/models';

@Component({
  selector: 'bz-building',
  imports: [RouterLink, HlmAlertImports, HlmBadgeImports, HlmButtonImports, HlmProgressImports, BazeShelfLoader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './building-page.html',
  host: { class: 'block min-h-0 flex-1 overflow-y-auto pb-8' },
})
export class BuildingPage {
  private readonly api = inject(BazeApi);
  protected readonly draft = signal<Draft | null | undefined>(undefined);

  constructor() {
    inject(ActivatedRoute).paramMap.pipe(
      map((params) => params.get('id') ?? ''),
      switchMap((id) => this.api.draft(id).pipe(catchError(() => of(null)))),
      takeUntilDestroyed(),
    ).subscribe((draft) => this.draft.set(draft));
  }
}
