import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'bz-shot',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
  template: `
    <span
      class="bg-card flex h-full flex-col gap-1.5 overflow-hidden rounded-lg border p-2"
      role="img"
      [attr.aria-label]="'Screenshot of the ' + name() + ' view'"
    >
      <span class="flex items-center gap-1">
        <span class="size-2.5 rounded-sm" [style.background]="accent()"></span>
        <span class="bg-muted h-1.5 w-2/5 rounded-sm"></span>
        <span class="ms-auto h-2.5 w-1/4 rounded-sm" [style.background]="accent()"></span>
      </span>
      <span class="grid grid-cols-3 gap-1">
        <span class="bg-muted h-4 rounded-sm"></span>
        <span class="bg-muted h-4 rounded-sm"></span>
        <span class="h-4 rounded-sm opacity-40" [style.background]="accent()"></span>
      </span>
      <span class="bg-border h-1.5 w-4/5 rounded-sm"></span>
      <span class="bg-border h-1.5 w-3/5 rounded-sm"></span>
      <span class="bg-border h-1.5 w-2/3 rounded-sm"></span>
    </span>
  `,
})
export class ShotPreview {
  readonly accent = input.required<string>();
  readonly name = input.required<string>();
}
