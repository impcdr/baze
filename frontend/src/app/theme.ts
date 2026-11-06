import { DOCUMENT } from '@angular/common';
import { Injectable, effect, inject, signal } from '@angular/core';

export type ColorMode = 'dark' | 'light';

const STORAGE_KEY = 'kiln.theme';
/** Clears a stuck dark preference once, then leaves later choices alone. */
const LIGHT_DEFAULT_KEY = 'kiln.theme.v2';

@Injectable({ providedIn: 'root' })
export class Theme {
  private readonly document = inject(DOCUMENT);

  readonly mode = signal<ColorMode>(this.read());

  constructor() {
    effect(() => {
      const dark = this.mode() === 'dark';
      this.document.documentElement.classList.toggle('dark', dark);
      localStorage.setItem(STORAGE_KEY, this.mode());
    });
  }

  toggle(): void {
    this.mode.update((mode) => (mode === 'dark' ? 'light' : 'dark'));
  }

  private read(): ColorMode {
    try {
      if (localStorage.getItem(LIGHT_DEFAULT_KEY) !== 'light') {
        localStorage.setItem(STORAGE_KEY, 'light');
        localStorage.setItem(LIGHT_DEFAULT_KEY, 'light');
        return 'light';
      }
      return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light';
    } catch {
      return 'light';
    }
  }
}
