import type {
  Account,
  Draft,
  Preset,
  ShelfApp,
  Shot,
  Suggestion,
  Workspace,
} from './models';

export const ACCOUNT: Account = {
  name: 'Lena Lindner',
  initials: 'LK',
  color: '#22c79b',
  ink: '#0b1b3f',
  email: 'hello@lindner-studio.de',
};

export const PRESETS: Preset[] = [
  { id: 'ocean', label: 'Ocean', color: '#2563eb' },
  { id: 'forest', label: 'Forest', color: '#15803d' },
  { id: 'sunset', label: 'Sunset', color: '#c2410c' },
  { id: 'plum', label: 'Plum', color: '#7c3aed' },
  { id: 'graphite', label: 'Graphite', color: '#334155' },
  { id: 'rose', label: 'Rose', color: '#be185d' },
];

export const SUGGESTIONS: Suggestion[] = [
  {
    id: 'watchlist',
    label: 'A stock watchlist with price alerts',
    prompt: 'A stock watchlist with price alerts when something drops.',
  },
  {
    id: 'shifts',
    label: 'Staff shifts for my café',
    prompt: 'Staff shifts for my café, so the week is covered.',
  },
  {
    id: 'stock',
    label: 'Stock room counts',
    prompt: 'Stock room counts for the studio supplies.',
  },
  {
    id: 'followups',
    label: 'Client follow-ups',
    prompt: 'Client follow-ups, the calls I still owe this week.',
  },
];

const invoices: ShelfApp = {
  id: 'studio',
  slug: 'studio-invoices',
  name: 'Studio Invoices',
  summary: 'Send invoices and remind late clients.',
  detail: 'Send invoices and remind late clients.',
  status: 'live',
  statusLabel: 'Live',
  labels: [
    { text: 'New', tone: 'secondary' },
    { text: 'Take a look', tone: 'warning' },
    { text: 'Live', tone: 'success' },
  ],
  preset: 'forest',
  color: '#15803d',
  icon: 'lucideReceipt',
  isNew: true,
  badge: 'New',
  progress: null,
  path: '/a/studio-invoices',
  external: true,
  sharedBy: null,
};

const watchlist: ShelfApp = {
  id: 'watchlist',
  slug: 'stock-watchlist',
  name: 'Stock watchlist',
  summary: 'Price alerts when a stock drops.',
  detail: 'Price alerts when a stock drops.',
  status: 'live',
  statusLabel: 'Live',
  labels: [{ text: 'Live', tone: 'success' }],
  preset: 'graphite',
  color: '#334155',
  icon: 'lucideTrendingUp',
  isNew: false,
  badge: null,
  progress: null,
  path: '/a/stock-watchlist',
  external: true,
  sharedBy: null,
};

const followups: ShelfApp = {
  id: 'followups',
  slug: 'client-follow-ups',
  name: 'Client follow-ups',
  summary: 'The client calls you still need to make.',
  detail: 'The client calls you still need to make.',
  status: 'live',
  statusLabel: 'Live',
  labels: [{ text: 'Live', tone: 'success' }],
  preset: 'ocean',
  color: '#2563eb',
  icon: 'lucideUsers',
  isNew: false,
  badge: null,
  progress: null,
  path: '/a/client-follow-ups',
  external: true,
  sharedBy: null,
};

const stock: ShelfApp = {
  id: 'stock',
  slug: 'stock-room',
  name: 'Stock room',
  summary: 'Counts for the studio supplies.',
  detail: 'Counts for the studio supplies.',
  status: 'attention',
  statusLabel: 'Take a look',
  labels: [{ text: 'Take a look', tone: 'warning' }],
  preset: 'plum',
  color: '#7c3aed',
  icon: 'lucidePackage',
  isNew: false,
  badge: null,
  progress: null,
  path: '/a/stock-room',
  external: true,
  sharedBy: null,
};

const shifts: ShelfApp = {
  id: 'shifts',
  slug: 'cafe-shifts',
  name: 'Café shifts',
  summary: 'Staff shifts so the café week is covered.',
  detail: 'Staff shifts so the café week is covered.',
  status: 'building',
  statusLabel: 'Being made',
  labels: [{ text: 'Being made', tone: 'secondary' }],
  preset: 'sunset',
  color: '#c2410c',
  icon: 'lucideCalendarDays',
  isNew: false,
  badge: null,
  progress: 68,
  path: '/building/shifts',
  external: false,
  sharedBy: null,
};

const expenses: ShelfApp = {
  id: 'expenses',
  slug: 'team-expenses',
  name: 'Team expenses',
  summary: 'Log what the team spends.',
  detail: 'Log what the team spends.',
  status: 'paused',
  statusLabel: 'Paused',
  labels: [{ text: 'Paused', tone: 'outline' }],
  preset: 'rose',
  color: '#be185d',
  icon: 'lucideWallet',
  isNew: false,
  badge: null,
  progress: null,
  path: '/a/team-expenses',
  external: true,
  sharedBy: null,
};

export const YOUR_APPS: ShelfApp[] = [invoices, watchlist, followups, stock, shifts, expenses];

export const FEATURED_IDS = ['studio', 'watchlist', 'stock', 'shifts'];

export const SHARED_APPS: ShelfApp[] = [
  {
    id: 'holiday',
    slug: 'holiday-cover',
    name: 'Holiday cover',
    summary: 'Who covers the studio while people are away.',
    detail: 'Who covers the studio while people are away.',
    status: 'live',
    statusLabel: 'Live',
    labels: [{ text: 'Live', tone: 'success' }],
    preset: 'ocean',
    color: '#2563eb',
    icon: 'lucideCalendarDays',
    isNew: false,
    badge: null,
    progress: null,
    path: '/a/holiday-cover',
    external: true,
    sharedBy: 'Nico Park',
  },
  {
    id: 'menu',
    slug: 'menu-board',
    name: 'Menu board',
    summary: 'The café menu, in one place.',
    detail: 'The café menu, in one place.',
    status: 'live',
    statusLabel: 'Live',
    labels: [{ text: 'Live', tone: 'success' }],
    preset: 'rose',
    color: '#be185d',
    icon: 'lucideUtensils',
    isNew: false,
    badge: null,
    progress: null,
    path: '/a/menu-board',
    external: true,
    sharedBy: 'Jules Berg',
  },
];

export const HOME_COPY = {
  greeting: 'Good afternoon, Lena',
  headline: 'What should we make today?',
  prompt: 'Invoices for my design studio. Send them, see who has paid, remind late clients by email.',
  suggestionsLabel: 'People are making:',
  shelfTitle: 'Your apps',
  seeAllLabel: 'See all 6',
};

const invoiceShots = (accent: string): Shot[] => [
  { id: 'invoices', name: 'Invoices', accent },
  { id: 'new', name: 'New invoice', accent },
  { id: 'remind', name: 'Reminder email', accent },
];

export function studioDraft(): Draft {
  const preset = PRESETS.find((item) => item.id === 'forest')!;
  return {
    id: 'studio',
    kicker: 'Step 1 of 3 · Describe',
    selectedPreset: 'forest',
    briefTitle: 'What I’m making',
    composerPlaceholder: 'Tell me what to change…',
    makeLabel: 'Looks right, make it',
    note: 'You’ll see screenshots here while we shape it. Once it’s made, your app opens in its own browser tab.',
    brief: [
      { label: 'Name', value: 'Studio Invoices', swatch: null },
      { label: 'Its one job', value: 'Send invoices', swatch: null },
      { label: 'Look', value: preset.label, swatch: preset.color },
      { label: 'Views', value: 'Invoices, New invoice, Reminder email', swatch: null },
      { label: 'Talks to', value: 'Your email only', swatch: null },
    ],
    messages: [
      {
        id: 'm1',
        role: 'you',
        text: 'Invoices for my design studio. Send them, see who has paid, and remind late clients by email.',
        shots: [],
        askPreset: false,
      },
      {
        id: 'm2',
        role: 'baze',
        text: 'Here’s a first look. Studio Invoices has one job, sending invoices, and three views:',
        shots: invoiceShots(preset.color),
        askPreset: true,
      },
      {
        id: 'm3',
        role: 'you',
        text: 'Reminders should come from hello@lindner-studio.de',
        shots: [],
        askPreset: false,
      },
    ],
    build: {
      kicker: 'Step 2 of 3 · Making it',
      title: 'Studio Invoices is taking shape',
      subtitle: 'About a minute left. You can close this page, we’ll email you when it’s ready.',
      steps: [
        { id: 'write', label: 'Writing it', state: 'done', progress: 100 },
        { id: 'try', label: 'Trying it safely', state: 'done', progress: 100 },
        { id: 'check', label: 'Checking it’s safe', state: 'active', progress: 55 },
        { id: 'ready', label: 'Ready for you', state: 'waiting', progress: 0 },
      ],
      noticeTitle: 'We stopped one thing',
      noticeBody:
        'Your app tried to send invoice details to an outside PDF service. We switched it to a built-in PDF maker, so your clients’ details stay with you. Nothing left the safe space.',
      waitingTitle: 'While you wait',
      waitingBody:
        'We’re creating test invoices, marking them paid and sending practice reminders, all inside a sealed space that can only reach your email.',
    },
    ready: {
      kicker: 'Step 3 of 3 · Ready',
      title: 'Studio Invoices is ready',
      address: 'baze.app/studio-invoices · Forest look',
      color: preset.color,
      icon: 'lucideReceipt',
      facts: [
        { label: 'Its one job', value: 'Send invoices', swatch: null },
        { label: 'Views', value: 'Invoices, New invoice, Reminder email', swatch: null },
        { label: 'Look', value: 'Forest', swatch: preset.color },
        { label: 'Reminders come from', value: 'hello@lindner-studio.de', swatch: null },
      ],
      openLabel: 'Open your app',
      openPath: '/a/studio-invoices',
      openHint: 'It opens in its own browser tab with example clients, so you can try it. Baze stays here.',
      safetyTitle: 'Safety check',
      checks: [
        { id: 'works', tone: 'pass', text: 'It works. We made, paid and reminded test invoices.' },
        { id: 'email', tone: 'pass', text: 'It only talks to your email.' },
        { id: 'place', tone: 'pass', text: 'Client details stay in Frankfurt, inside the EU.' },
        { id: 'pdf', tone: 'changed', text: 'An outside PDF service was swapped for a built-in one.' },
      ],
      publishLabel: 'Put it live',
      shareLabel: 'Share the safety check',
    },
  };
}

export function shiftsDraft(): Draft {
  const preset = PRESETS.find((item) => item.id === 'sunset')!;
  return {
    id: 'shifts',
    kicker: 'Step 1 of 3 · Describe',
    selectedPreset: 'sunset',
    briefTitle: 'What I’m making',
    composerPlaceholder: 'Tell me what to change…',
    makeLabel: 'Looks right, make it',
    note: 'You’ll see screenshots here while we shape it. Once it’s made, your app opens in its own browser tab.',
    brief: [
      { label: 'Name', value: 'Café shifts', swatch: null },
      { label: 'Its one job', value: 'Cover the week', swatch: null },
      { label: 'Look', value: preset.label, swatch: preset.color },
      { label: 'Views', value: 'This week, Open shift', swatch: null },
      { label: 'Talks to', value: 'Your email only', swatch: null },
    ],
    messages: [
      {
        id: 's1',
        role: 'you',
        text: 'Staff shifts for my café, so the week is covered.',
        shots: [],
        askPreset: false,
      },
      {
        id: 's2',
        role: 'baze',
        text: 'Café shifts has one job, covering the week. Two views so far:',
        shots: [
          { id: 'week', name: 'This week', accent: preset.color },
          { id: 'open', name: 'Open shift', accent: preset.color },
        ],
        askPreset: true,
      },
    ],
    build: {
      kicker: 'Step 2 of 3 · Making it',
      title: 'Café shifts is taking shape',
      subtitle: 'About a minute left. You can close this page, we’ll email you when it’s ready.',
      steps: [
        { id: 'write', label: 'Writing it', state: 'done', progress: 100 },
        { id: 'try', label: 'Trying it safely', state: 'done', progress: 100 },
        { id: 'check', label: 'Checking it’s safe', state: 'active', progress: 55 },
        { id: 'ready', label: 'Ready for you', state: 'waiting', progress: 0 },
      ],
      noticeTitle: 'We stopped one thing',
      noticeBody:
        'The rota tried to load names from an outside scheduling site. We kept the names you already typed, and nothing left the safe space.',
      waitingTitle: 'While you wait',
      waitingBody: 'We’re filling a practice week and checking that every open shift has a person.',
    },
    ready: {
      kicker: 'Step 3 of 3 · Ready',
      title: 'Café shifts is ready',
      address: 'baze.app/cafe-shifts · Sunset look',
      color: preset.color,
      icon: 'lucideCalendarDays',
      facts: [
        { label: 'Its one job', value: 'Cover the week', swatch: null },
        { label: 'Views', value: 'This week, Open shift', swatch: null },
        { label: 'Look', value: preset.label, swatch: preset.color },
        { label: 'Talks to', value: 'Your email only', swatch: null },
      ],
      openLabel: 'Open your app',
      openPath: '/a/cafe-shifts',
      openHint: 'It opens in its own browser tab. Baze stays here.',
      safetyTitle: 'Safety check',
      checks: [
        { id: 'works', tone: 'pass', text: 'It works. We filled a practice week.' },
        { id: 'email', tone: 'pass', text: 'It only talks to your email.' },
        { id: 'outside', tone: 'changed', text: 'An outside scheduling site was left unused.' },
      ],
      publishLabel: 'Put it live',
      shareLabel: 'Share the safety check',
    },
  };
}

export const WORKSPACES: Record<string, Workspace> = {
  'studio-invoices': {
    slug: 'studio-invoices',
    name: 'Studio Invoices',
    preset: 'forest',
    color: '#15803d',
    icon: 'lucideReceipt',
    primaryAction: 'New invoice',
    secondaryAction: 'Export',
    madeWithLabel: 'Made with baze · safety check',
    madeWithPath: '/ready/studio',
    sections: [
      {
        id: 'invoices',
        label: 'Invoices',
        panel: {
          title: 'Invoices',
          empty: null,
          stats: [
            { label: 'Waiting to be paid', value: '€8,240', note: null },
            { label: 'Paid in November', value: '€14,900', note: '+18% on October' },
            { label: 'Late', value: '2 clients', note: null },
            { label: 'Average time to pay', value: '11 days', note: null },
          ],
          columns: ['No.', 'Client', 'Amount', 'Status'],
          rows: [
            { id: '0141', cells: ['#0141', 'Nordlicht Café', '€2,400'], badge: null, action: '12 days late · Remind' },
            { id: '0140', cells: ['#0140', 'Weber & Söhne', '€980'], badge: { label: '5 days late', tone: 'warning' }, action: null },
            { id: '0139', cells: ['#0139', 'Hofmann Architects', '€4,180'], badge: { label: 'Due in 6 days', tone: 'muted' }, action: null },
            { id: '0138', cells: ['#0138', 'Saar Bikes', '€1,660'], badge: { label: 'Paid 2 Nov', tone: 'success' }, action: null },
            { id: '0137', cells: ['#0137', 'Kaffeehaus Lindner', '€720'], badge: { label: 'Paid 30 Oct', tone: 'success' }, action: null },
          ],
          chartTitle: 'Paid per week',
          chartStart: '7 weeks ago',
          chartEnd: 'This week · €4,100',
          bars: [
            { height: 42, current: false },
            { height: 55, current: false },
            { height: 38, current: false },
            { height: 64, current: false },
            { height: 58, current: false },
            { height: 76, current: false },
            { height: 92, current: true },
          ],
        },
      },
      {
        id: 'clients',
        label: 'Clients',
        panel: { title: 'Clients', empty: 'The people on your invoices show up here.', stats: [], columns: [], rows: [], chartTitle: '', chartStart: '', chartEnd: '', bars: [] },
      },
      {
        id: 'reminders',
        label: 'Reminders',
        panel: { title: 'Reminders', empty: 'Late invoices get a reminder from your email.', stats: [], columns: [], rows: [], chartTitle: '', chartStart: '', chartEnd: '', bars: [] },
      },
      {
        id: 'settings',
        label: 'Settings',
        panel: { title: 'Settings', empty: 'Reminders come from hello@lindner-studio.de.', stats: [], columns: [], rows: [], chartTitle: '', chartStart: '', chartEnd: '', bars: [] },
      },
    ],
  },
};

export const PROMPT_DRAFTS: { match: string; id: string }[] = [
  { match: 'invoice', id: 'studio' },
  { match: 'shift', id: 'shifts' },
  { match: 'café', id: 'shifts' },
  { match: 'cafe', id: 'shifts' },
];
