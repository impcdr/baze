import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmDialogImports } from '@spartan-ng/helm/dialog';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { HlmToasterImports } from '@spartan-ng/helm/sonner';
import { BazeApi } from '../api/baze-api';
import { CURRENT_USER } from '../api/current-user';
import { BazeLogo } from '../baze/brand';
import { Theme } from '../theme';

@Component({
  selector: 'bz-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, BazeLogo, HlmDialogImports, HlmButtonImports, HlmInputImports, HlmToasterImports],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './shell.html',
  host: {
    class: 'block min-h-svh bg-background text-foreground',
    '[attr.data-user]': 'signedInEmail',
  },
})
export class Shell {
  private readonly api = inject(BazeApi);
  protected readonly theme = inject(Theme);
  protected readonly signedInEmail = CURRENT_USER.email;
  protected readonly account = toSignal(this.api.account());
}
