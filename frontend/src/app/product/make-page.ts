import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { catchError, map, of, switchMap } from 'rxjs';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmDialogImports } from '@spartan-ng/helm/dialog';
import { BazeLogo } from '../baze/brand';
import { BazeApi } from '../api/baze-api';
import type { Draft, Shot } from '../api/models';
import { BAZE_ICONS } from './icons';
import { ShotPreview } from './shot-preview';

@Component({
  selector: 'bz-make',
  imports: [NgIcon, HlmBadgeImports, HlmButtonImports, HlmDialogImports, BazeLogo, ShotPreview],
  providers: [provideIcons(BAZE_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './make-page.html',
  host: { class: 'block min-h-0 flex-1 overflow-y-auto pb-8' },
})
export class MakePage {
  private readonly api = inject(BazeApi);
  private readonly router = inject(Router);

  protected readonly draft = signal<Draft | null | undefined>(undefined);
  protected readonly presets = signal<{ id: string; label: string; color: string }[]>([]);
  protected readonly reply = signal('');
  protected readonly openShot = signal<Shot | null>(null);

  constructor() {
    this.api.presets().pipe(takeUntilDestroyed()).subscribe((presets) => this.presets.set(presets));
    inject(ActivatedRoute).paramMap.pipe(
      map((params) => params.get('id') ?? ''),
      switchMap((id) => this.api.draft(id).pipe(catchError(() => of(null)))),
      takeUntilDestroyed(),
    ).subscribe((draft) => this.draft.set(draft));
  }

  protected choose(preset: string): void {
    const draft = this.draft();
    if (!draft) return;
    this.api.choosePreset(draft.id, preset).subscribe((next) => this.draft.set(next));
  }

  protected send(): void {
    const draft = this.draft();
    const text = this.reply().trim();
    if (!draft || !text) return;
    this.reply.set('');
    this.api.sendMessage(draft.id, text).subscribe((next) => this.draft.set(next));
  }

  protected build(): void {
    const draft = this.draft();
    if (!draft) return;
    void this.router.navigate(['/building', draft.id]);
  }

  protected focusShot(shot: Shot): void {
    this.openShot.set(shot);
  }
}
