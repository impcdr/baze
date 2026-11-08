import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { BAZE_ICONS } from './icons';

@Component({
  selector: 'bz-home',
  imports: [RouterLink, NgIcon, HlmButtonImports],
  providers: [provideIcons(BAZE_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './home-page.html',
  host: { class: 'flex min-h-0 flex-1 items-start overflow-y-auto' },
})
export class HomePage {}
