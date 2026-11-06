import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { toast } from '@spartan-ng/brain/sonner';
import { catchError, map, of, switchMap } from 'rxjs';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { BazeAppTile } from '../baze/brand';
import { BazeApi } from '../api/baze-api';
import type { Draft } from '../api/models';
import { BAZE_ICONS } from './icons';

@Component({
  selector: 'bz-ready',
  imports: [NgIcon, HlmBadgeImports, HlmButtonImports, BazeAppTile],
  providers: [provideIcons(BAZE_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './ready-page.html',
  host: { class: 'block min-h-0 flex-1 overflow-y-auto pb-8' },
})
export class ReadyPage {
  private readonly api = inject(BazeApi);
  private readonly router = inject(Router);
  protected readonly draft = signal<Draft | null | undefined>(undefined);

  constructor() {
    inject(ActivatedRoute).paramMap.pipe(
      map((params) => params.get('id') ?? ''),
      switchMap((id) => this.api.draft(id).pipe(catchError(() => of(null)))),
      takeUntilDestroyed(),
    ).subscribe((draft) => this.draft.set(draft));
  }

  protected publish(): void {
    const draft = this.draft();
    if (!draft) return;
    this.api.publish(draft.id).subscribe(() => {
      void this.router.navigate(['/apps']);
    });
  }

  protected share(): void {
    const draft = this.draft();
    if (!draft) return;
    this.api.shareSafety(draft.id).subscribe((result) => toast(result.message));
  }
}
