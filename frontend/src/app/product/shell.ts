import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { toast } from '@spartan-ng/brain/sonner';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmDialogImports } from '@spartan-ng/helm/dialog';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { HlmRadioGroupImports } from '@spartan-ng/helm/radio-group';
import { HlmToasterImports } from '@spartan-ng/helm/sonner';
import { take } from 'rxjs';
import { BazeApi } from '../api/baze-api';
import type { Account } from '../api/models';
import { BazeLogo } from '../baze/brand';
import { Theme } from '../theme';

@Component({
  selector: 'bz-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, BazeLogo, HlmDialogImports, HlmButtonImports, HlmInputImports, HlmRadioGroupImports, HlmToasterImports],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './shell.html',
  host: {
    class: 'block min-h-svh bg-background text-foreground',
    '[attr.data-user]': 'account()?.email ?? ""',
  },
})
export class Shell {
  private readonly api = inject(BazeApi);
  protected readonly theme = inject(Theme);
  protected readonly account = signal<Account | null>(null);
  protected readonly switching = signal(false);

  constructor() {
    this.api
      .account()
      .pipe(take(1), takeUntilDestroyed())
      .subscribe((person) => this.account.set(person));
  }

  protected switchAccount(email: string): void {
    const person = this.account();
    if (!person || this.switching() || email === person.email) return;
    this.switching.set(true);
    this.api.useAccount(email).subscribe({
      next: () => location.reload(),
      error: () => {
        this.switching.set(false);
        toast('The account did not switch.');
      },
    });
  }
}
