import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Title } from '@angular/platform-browser';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { provideIcons } from '@ng-icons/core';
import { toast } from '@spartan-ng/brain/sonner';
import { catchError, map, of, switchMap } from 'rxjs';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmEmptyImports } from '@spartan-ng/helm/empty';
import { BazeAppTile, BazeLogo } from '../baze/brand';
import { BazeApi } from '../api/baze-api';
import type { Workspace, WorkspaceSection } from '../api/models';
import { BAZE_ICONS } from './icons';

@Component({
  selector: 'bz-open-app',
  imports: [RouterLink, HlmBadgeImports, HlmButtonImports, HlmEmptyImports, BazeAppTile, BazeLogo],
  providers: [provideIcons(BAZE_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './open-app-page.html',
  host: {
    class: 'block min-h-full bg-background text-foreground',
    '[attr.data-app]': 'preset()',
  },
})
export class OpenAppPage {
  private readonly api = inject(BazeApi);
  private readonly title = inject(Title);

  protected readonly workspace = signal<Workspace | null | undefined>(undefined);
  protected readonly sectionId = signal<string | null>(null);
  protected readonly preset = signal<string | null>(null);

  constructor() {
    inject(ActivatedRoute).paramMap.pipe(
      map((params) => params.get('appId') ?? ''),
      switchMap((appId) => this.api.workspace(appId).pipe(catchError(() => of(null)))),
      takeUntilDestroyed(),
    ).subscribe((workspace) => {
      this.workspace.set(workspace);
      if (workspace) {
        this.preset.set(workspace.preset);
        this.sectionId.set(workspace.sections[0]?.id ?? null);
        this.title.setTitle(workspace.name);
      }
    });
  }

  protected section(): WorkspaceSection | null {
    const workspace = this.workspace();
    if (!workspace) return null;
    return workspace.sections.find((item) => item.id === this.sectionId()) ?? workspace.sections[0] ?? null;
  }

  protected choose(id: string): void {
    this.sectionId.set(id);
  }

  protected act(label: string): void {
    toast(label);
  }
}
