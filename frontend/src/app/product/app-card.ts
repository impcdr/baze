import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmDropdownMenuImports } from '@spartan-ng/helm/dropdown-menu';
import { BazeAppTile } from '../baze/brand';
import type { AppLabel, ShelfApp } from '../api/models';
import { BAZE_ICONS } from './icons';

@Component({
  selector: 'bz-app-card',
  imports: [NgTemplateOutlet, RouterLink, NgIcon, HlmBadgeImports, HlmButtonImports, HlmDropdownMenuImports, BazeAppTile],
  providers: [provideIcons(BAZE_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app-card.html',
  host: { class: 'bz-app-card block h-40' },
})
export class AppCard {
  readonly app = input.required<ShelfApp>();

  protected labels(): AppLabel[] {
    const app = this.app();
    if (app.labels?.length) return app.labels;
    const labels: AppLabel[] = [];
    if (app.badge) labels.push({ text: app.badge, tone: 'secondary' });
    if (app.statusLabel) {
      labels.push({
        text: app.statusLabel,
        tone: app.status === 'live' ? 'success' : app.status === 'attention' ? 'warning' : app.status === 'building' ? 'secondary' : 'outline',
      });
    }
    return labels;
  }
}
