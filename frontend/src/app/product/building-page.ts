import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { catchError, distinctUntilChanged, map, of, switchMap, takeWhile, timer } from 'rxjs';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { BazeShelfLoader } from '../baze/brand';
import { BazeApi } from '../api/baze-api';
import type { AppManage } from '../api/models';

@Component({
  selector: 'bz-building',
  imports: [RouterLink, HlmButtonImports, BazeShelfLoader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './building-page.html',
  host: { class: 'block min-h-0 flex-1 overflow-y-auto pb-8' },
})
export class BuildingPage {
  private readonly api = inject(BazeApi);
  private readonly router = inject(Router);

  protected readonly page = signal<AppManage | null | undefined>(undefined);

  constructor() {
    inject(ActivatedRoute)
      .paramMap.pipe(
        map((params) => params.get('id') ?? ''),
        distinctUntilChanged(),
        switchMap((id) =>
          timer(0, 1000).pipe(
            switchMap(() => this.api.manage(id).pipe(catchError(() => of(null)))),
            takeWhile((page) => page?.status === 'building', true),
          ),
        ),
        takeUntilDestroyed(),
      )
      .subscribe((page) => {
        this.page.set(page);
        if (page?.status === 'live') {
          void this.router.navigate(['/apps', page.id], { replaceUrl: true });
        }
      });
  }
}
