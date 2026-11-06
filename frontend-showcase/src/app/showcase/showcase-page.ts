import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { lucideCalendarDays, lucideMoon, lucidePlus, lucideReceipt, lucideShieldCheck, lucideSun } from '@ng-icons/lucide';
import { barY, defineChart, lineY } from '@tanstack/charts';
import { scaleBand } from '@tanstack/charts/scales/band';
import { scaleLinear } from '@tanstack/charts/scales/linear';
import { toast } from '@spartan-ng/brain/sonner';
import { HlmAlertImports } from '@spartan-ng/helm/alert';
import { HlmAttachmentImports } from '@spartan-ng/helm/attachment';
import { HlmAvatarImports } from '@spartan-ng/helm/avatar';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmBubbleImports } from '@spartan-ng/helm/bubble';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmCardImports } from '@spartan-ng/helm/card';
import { HlmChartImports } from '@spartan-ng/helm/chart';
import { HlmDialogImports } from '@spartan-ng/helm/dialog';
import { HlmDropdownMenuImports } from '@spartan-ng/helm/dropdown-menu';
import { HlmEmptyImports } from '@spartan-ng/helm/empty';
import { HlmFieldImports } from '@spartan-ng/helm/field';
import { HlmInputGroupImports } from '@spartan-ng/helm/input-group';
import { HlmKbdImports } from '@spartan-ng/helm/kbd';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { HlmItemImports } from '@spartan-ng/helm/item';
import { HlmMessageImports } from '@spartan-ng/helm/message';
import { HlmMessageScrollerImports } from '@spartan-ng/helm/message-scroller';
import { HlmNativeSelectImports } from '@spartan-ng/helm/native-select';
import { HlmProgressImports } from '@spartan-ng/helm/progress';
import { HlmSeparatorImports } from '@spartan-ng/helm/separator';
import { HlmSheetImports } from '@spartan-ng/helm/sheet';
import { HlmSidebarImports } from '@spartan-ng/helm/sidebar';
import { HlmSkeletonImports } from '@spartan-ng/helm/skeleton';
import { HlmToasterImports } from '@spartan-ng/helm/sonner';
import { HlmSpinnerImports } from '@spartan-ng/helm/spinner';
import { HlmTableImports } from '@spartan-ng/helm/table';
import { HlmTabsImports } from '@spartan-ng/helm/tabs';
import { HlmTextareaImports } from '@spartan-ng/helm/textarea';
import { HlmTooltipImports } from '@spartan-ng/helm/tooltip';
import { HlmToggleGroupImports } from '@spartan-ng/helm/toggle-group';
import { BazeBrandImports } from '@baze/brand';
import { Theme } from '@baze/theme';
import { SpartanExtras } from './extras-section';

interface InvoiceWeek {
  week: string;
  amount: number;
  current: boolean;
}

interface PricePoint {
  day: string;
  price: number;
}

const INVOICES: InvoiceWeek[] = [
  { week: 'Mon', amount: 1200, current: false },
  { week: 'Tue', amount: 1800, current: false },
  { week: 'Wed', amount: 1600, current: false },
  { week: 'Thu', amount: 2400, current: false },
  { week: 'Fri', amount: 3100, current: false },
  { week: 'Sat', amount: 2800, current: false },
  { week: 'Sun', amount: 4100, current: true },
];

const PRICES: PricePoint[] = [
  { day: '1', price: 12 },
  { day: '2', price: 14 },
  { day: '3', price: 13 },
  { day: '4', price: 18 },
  { day: '5', price: 17 },
  { day: '6', price: 21 },
  { day: '7', price: 24 },
];

function shot(title: string, fill: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 100">
    <rect width="160" height="100" fill="#F7F8FA"/>
    <rect x="10" y="10" width="140" height="16" rx="4" fill="#E8ECF2"/>
    <rect x="14" y="14" width="28" height="8" rx="2" fill="${fill}"/>
    <rect x="10" y="34" width="86" height="56" rx="6" fill="#FFFFFF" stroke="#D7DEE8"/>
    <rect x="18" y="44" width="48" height="6" rx="2" fill="#0B1B3F"/>
    <rect x="18" y="56" width="70" height="4" rx="2" fill="#C5CEDB"/>
    <rect x="18" y="66" width="54" height="4" rx="2" fill="#C5CEDB"/>
    <rect x="104" y="34" width="46" height="24" rx="6" fill="${fill}"/>
    <text x="127" y="49" text-anchor="middle" fill="#ffffff" font-size="8" font-family="sans-serif">${title}</text>
  </svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

export const PRESETS = [
  { id: 'ocean', label: 'Ocean', color: '#2563eb' },
  { id: 'forest', label: 'Forest', color: '#15803d' },
  { id: 'sunset', label: 'Sunset', color: '#c2410c' },
  { id: 'plum', label: 'Plum', color: '#7c3aed' },
  { id: 'graphite', label: 'Graphite', color: '#334155' },
  { id: 'rose', label: 'Rose', color: '#be185d' },
] as const;

export const SHOTS = [
  { id: 'home', title: 'Home', src: shot('Home', '#2563eb') },
  { id: 'invoice', title: 'Invoice', src: shot('Invoice', '#15803d') },
] as const;

@Component({
  selector: 'app-showcase-page',
  imports: [
    RouterLink,
    NgIcon,
    ...BazeBrandImports,
    ...HlmAlertImports,
    ...HlmAttachmentImports,
    ...HlmAvatarImports,
    ...HlmBadgeImports,
    ...HlmBubbleImports,
    ...HlmButtonImports,
    ...HlmCardImports,
    ...HlmChartImports,
    ...HlmDialogImports,
    ...HlmDropdownMenuImports,
    ...HlmEmptyImports,
    ...HlmFieldImports,
    ...HlmInputGroupImports,
    ...HlmInputImports,
    ...HlmItemImports,
    ...HlmMessageImports,
    ...HlmMessageScrollerImports,
    ...HlmNativeSelectImports,
    ...HlmProgressImports,
    ...HlmSeparatorImports,
    ...HlmSheetImports,
    ...HlmSidebarImports,
    ...HlmSkeletonImports,
    ...HlmToasterImports,
    ...HlmSpinnerImports,
    ...HlmTableImports,
    ...HlmTabsImports,
    ...HlmTextareaImports,
    ...HlmTooltipImports,
    ...HlmKbdImports,
    ...HlmToggleGroupImports,
    SpartanExtras,
  ],
  providers: [provideIcons({ lucideCalendarDays, lucideMoon, lucidePlus, lucideReceipt, lucideShieldCheck, lucideSun })],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './showcase-page.html',
  host: { class: 'block min-h-full bg-background text-foreground' },
})
export class ShowcasePage {
  protected readonly theme = inject(Theme);
  protected readonly presets = PRESETS;
  protected readonly shots = SHOTS;
  protected readonly preset = signal<string>('ocean');
  protected readonly presetColor = computed(
    () => this.presets.find((look) => look.id === this.preset())?.color ?? this.presets[0].color,
  );
  protected readonly choice = signal<string>('website');
  protected readonly prompt = signal('');
  protected readonly openShot = signal<(typeof SHOTS)[number]>(SHOTS[0]);
  protected readonly progress = signal(68);
  protected readonly you = { name: 'Ada Holm', initials: 'AH', role: 'You', color: '#1a5ce6', ink: '#ffffff' };
  protected readonly people = [
    { name: 'Nico Park', initials: 'NP', role: 'Can edit', color: '#8db0ff', ink: '#0b1b3f' },
    { name: 'Jules Berg', initials: 'JB', role: 'Can look', color: '#22c79b', ink: '#0b1b3f' },
    { name: 'Sam Okonkwo', initials: 'SO', role: 'Can look', color: '#0b1b3f', ink: '#ffffff' },
  ];

  protected readonly barChart = {
    definition: defineChart({
      marks: [
        barY(INVOICES, {
          x: 'week',
          y: 'amount',
          fill: (row) => (row.current ? 'var(--chart-1)' : 'var(--muted)'),
          radius: 6,
        }),
      ],
      scales: {
        x: { scale: () => scaleBand().padding(0.28) },
        y: { scale: scaleLinear, nice: true, grid: true },
      },
    }),
    ariaLabel: 'Invoices rising to 4100 this week',
    height: 220,
  };

  protected readonly lineChart = {
    definition: defineChart({
      marks: [lineY(PRICES, { x: 'day', y: 'price', stroke: 'var(--chart-1)', strokeWidth: 2 })],
      scales: {
        x: { scale: () => scaleBand().padding(0.4) },
        y: { scale: scaleLinear, nice: true, grid: true },
      },
    }),
    ariaLabel: 'Price over seven days',
    height: 220,
  };

  protected setPreset(value: string | string[] | null | undefined): void {
    if (typeof value === 'string' && value) {
      this.preset.set(value);
    }
  }

  protected setChoice(value: string | string[] | null | undefined): void {
    if (typeof value === 'string' && value) {
      this.choice.set(value);
    }
  }

  protected chooseShot(shotItem: (typeof SHOTS)[number]): void {
    this.openShot.set(shotItem);
  }

  protected usePrompt(value: string): void {
    this.prompt.set(value);
  }

  protected announce(): void {
    toast.success('Your app is live.');
  }
}
