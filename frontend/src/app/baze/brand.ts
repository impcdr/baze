import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { NgIcon } from '@ng-icons/core';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';

@Component({
  selector: 'bz-logo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'bz-logo',
    role: 'img',
    '[attr.aria-label]': '"baze"',
    '[class.bz-logo--ondark]': 'tone() === "on-dark"',
    '[style.gap.px]': 'wordSize() / 3',
  },
  template: `
    <svg [attr.width]="markWidth()" [attr.height]="markHeight()" viewBox="4 42 94 50" aria-hidden="true">
      <rect class="s" x="6" y="80" width="88" height="8" rx="4"></rect>
      <rect class="a" x="9" y="52" width="26" height="26" rx="7"></rect>
      <rect class="b" x="38" y="52" width="26" height="26" rx="7"></rect>
      <rect class="c" x="70" y="52" width="26" height="26" rx="7" transform="rotate(-12 70 78)"></rect>
    </svg>
    @if (word()) {
      <span class="bz-logo__word" [style.font-size.px]="wordSize()">baze</span>
    }
  `,
})
export class BazeLogo {
  readonly word = input(true);
  /** Wordmark size in px. The shelf mark stays at the same ratio: 52×28 beside 30px type. */
  readonly wordSize = input(30);
  readonly tone = input<'default' | 'on-dark'>('default');
  protected readonly markWidth = computed(() => Math.round((this.wordSize() * 52) / 30));
  protected readonly markHeight = computed(() => Math.round((this.wordSize() * 28) / 30));
}

@Component({
  selector: 'bz-logo-reveal',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'bz-logo bz-logo-reveal', role: 'img', 'aria-label': 'baze' },
  template: `
    <svg width="104" height="56" viewBox="4 42 94 50" aria-hidden="true">
      <rect class="s" x="6" y="80" width="88" height="8" rx="4"></rect>
      <rect class="a" x="9" y="52" width="26" height="26" rx="7"></rect>
      <rect class="b" x="38" y="52" width="26" height="26" rx="7"></rect>
      <rect class="c" x="70" y="52" width="26" height="26" rx="7"></rect>
    </svg>
  `,
})
export class BazeLogoReveal {}

@Component({
  selector: 'bz-app-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'inline-flex', role: 'img', 'aria-label': 'Baze app icon' },
  template: `
    <svg [attr.width]="size()" [attr.height]="size()" viewBox="0 0 100 100" aria-hidden="true">
      <rect width="100" height="100" rx="24" fill="var(--primary)"></rect>
      <rect x="16" y="70" width="68" height="7" rx="3.5" fill="#fff"></rect>
      <rect x="19" y="47" width="20" height="20" rx="5.5" fill="#fff"></rect>
      <rect x="42" y="47" width="20" height="20" rx="5.5" fill="#C9D8FF"></rect>
      <rect x="66" y="47" width="20" height="20" rx="5.5" fill="#22C79B" transform="rotate(-12 66 67)"></rect>
    </svg>
  `,
})
export class BazeAppIcon {
  readonly size = input(64);
}

@Component({
  selector: 'bz-app-tile',
  imports: [NgIcon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'bz-app-tile',
    role: 'img',
    '[attr.aria-label]': 'label()',
    '[style.background]': 'color()',
    '[style.width.px]': 'size()',
    '[style.height.px]': 'size()',
    '[style.border-radius.px]': 'radius()',
  },
  template: `<ng-icon [name]="icon()" [style.font-size.px]="iconSize()" />`,
})
export class BazeAppTile {
  /** The app's own colour. */
  readonly color = input.required<string>();
  /** A Lucide icon name, such as lucideReceipt. */
  readonly icon = input.required<string>();
  readonly size = input(56);
  readonly label = input('App');
  protected readonly radius = computed(() => Math.round(this.size() * 0.36));
  protected readonly iconSize = computed(() => Math.round(this.size() * 0.46));
}

@Component({
  selector: 'bz-shelf-loader',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { role: 'status', '[attr.aria-label]': 'label()', '[class]': 'size() === "lg" ? "bz-loader bz-loader--lg" : "bz-loader"' },
  template: `
    <span class="bz-loader__tiles"><span></span><span></span><span></span></span>
    <span class="bz-loader__shelf"></span>
  `,
})
export class BazeShelfLoader {
  readonly size = input<'sm' | 'lg'>('sm');
  readonly label = input('Loading');
}

@Component({
  selector: 'bz-build-sequence',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex flex-col items-center gap-4">
      <span class="bz-logo bz-build" role="img" aria-label="Your new app hovering over its place on your shelf, then landing">
        <svg width="220" height="190" viewBox="0 4 100 88" aria-hidden="true" style="overflow: visible">
          <rect class="s" x="6" y="80" width="88" height="8" rx="4"></rect>
          <rect class="a" x="9" y="52" width="26" height="26" rx="7"></rect>
          <rect class="b" x="38" y="52" width="26" height="26" rx="7"></rect>
          <rect class="slot" x="69" y="53" width="24" height="24" rx="6" fill="none" style="stroke: var(--chart-2); stroke-width: 2.5"></rect>
          <path class="lines" d="M76 6 V10 M83 4 V10 M90 6 V10" style="stroke: var(--success); stroke-width: 2.5; stroke-linecap: round"></path>
          <rect class="c tile" x="70" y="52" width="26" height="26" rx="7"></rect>
        </svg>
      </span>
      <div class="bz-steps w-full max-w-xl">
        @for (step of steps; track step) {
          <div class="bz-steps__item">
            <div class="bz-steps__bar"><span></span></div>
            {{ step }}
          </div>
        }
      </div>
    </div>
  `,
})
export class BazeBuildSequence {
  readonly steps = ['Writing it', 'Trying it safely', 'Checking it’s safe', 'Ready for you'];
}

@Component({
  selector: 'bz-blocked-call',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="bz-blocked" role="img" aria-label="Your app tried to reach an unknown site; the wall stopped it">
      <svg width="360" height="150" viewBox="0 0 300 125">
        <rect x="20" y="38" width="50" height="50" rx="15" style="fill: var(--primary)"></rect>
        <path d="M36 54 H54 M36 63 H54 M36 72 H46" style="stroke: var(--primary-foreground); stroke-width: 3; stroke-linecap: round"></path>
        <rect class="flash" x="140" y="14" width="34" height="96" rx="17" style="fill: var(--bz-soft)"></rect>
        <rect class="wall" x="150" y="22" width="14" height="80" rx="7" style="fill: var(--foreground)"></rect>
        <circle cx="248" cy="62" r="26" fill="none" style="stroke: var(--chart-2); stroke-width: 3; stroke-dasharray: 6 5"></circle>
        <text x="248" y="70" text-anchor="middle" style="fill: var(--muted-foreground); font-family: var(--font-display), sans-serif; font-size: var(--bz-text-heading); font-weight: 800">?</text>
        <circle class="packet" cx="80" cy="62" r="7" style="fill: var(--warning)"></circle>
        <g class="safe">
          <rect x="111" y="104" width="92" height="20" rx="10" style="fill: var(--warning)"></rect>
          <text x="157" y="118" text-anchor="middle" style="fill: #0b1b3f; font-size: var(--bz-text-meta); font-weight: 700">Stopped</text>
        </g>
      </svg>
    </span>
  `,
})
export class BazeBlockedCall {}

@Component({
  selector: 'bz-check-draw',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'bz-check', role: 'img', 'aria-label': 'Check passed' },
  template: `
    <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
      <circle cx="14" cy="14" r="14"></circle>
      <path d="M8 14.5 L12 18.5 L20 10"></path>
    </svg>
  `,
})
export class BazeCheckDraw {}

@Component({
  selector: 'bz-live-pulse',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'bz-live', role: 'img', 'aria-label': 'Live' },
  template: '',
})
export class BazeLivePulse {}

@Component({
  selector: 'bz-go-live',
  imports: [HlmButtonImports, HlmBadgeImports],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'bz-golive' },
  template: `
    <span class="bz-golive__burst" aria-hidden="true">
      @for (tile of tiles; track tile) {
        <i></i>
      }
    </span>
    <button hlmBtn type="button" size="lg">Put it live</button>
    <span hlmBadge variant="success"><span class="bz-live"></span> Live</span>
  `,
})
export class BazeGoLive {
  readonly tiles = [1, 2, 3, 4, 5, 6, 7, 8];
}

export const BazeBrandImports = [
  BazeLogo,
  BazeLogoReveal,
  BazeAppIcon,
  BazeAppTile,
  BazeShelfLoader,
  BazeBuildSequence,
  BazeBlockedCall,
  BazeCheckDraw,
  BazeLivePulse,
  BazeGoLive,
] as const;
