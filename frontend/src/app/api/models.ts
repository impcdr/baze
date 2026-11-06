export type AppStatus = 'live' | 'building' | 'attention' | 'paused';
export type PresetId = 'ocean' | 'forest' | 'sunset' | 'plum' | 'graphite' | 'rose';
export type AppLabelTone = 'default' | 'secondary' | 'success' | 'warning' | 'outline';

export interface AppLabel {
  text: string;
  tone: AppLabelTone;
}

export interface Account {
  name: string;
  initials: string;
  color: string;
  ink: string;
  email: string;
}

export interface ShelfApp {
  id: string;
  slug: string;
  name: string;
  summary: string;
  detail: string;
  status: AppStatus;
  statusLabel: string;
  labels: AppLabel[];
  preset: PresetId;
  color: string;
  icon: string;
  isNew: boolean;
  badge: string | null;
  progress: number | null;
  path: string | null;
  external: boolean;
  sharedBy: string | null;
}

export interface Suggestion {
  id: string;
  label: string;
  prompt: string;
}

export interface HomePayload {
  greeting: string;
  headline: string;
  prompt: string;
  suggestionsLabel: string;
  suggestions: Suggestion[];
  shelfTitle: string;
  seeAllLabel: string;
  featured: ShelfApp[];
}

export interface ShelfPayload {
  title: string;
  summary: string;
  makeLabel: string;
  filters: { id: string; label: string }[];
  empty: string;
  apps: ShelfApp[];
  sharedTitle: string;
  sharedSummary: string;
  shared: ShelfApp[];
}

export interface Preset {
  id: PresetId;
  label: string;
  color: string;
}

export interface Shot {
  id: string;
  name: string;
  accent: string;
}

export interface DraftMessage {
  id: string;
  role: 'you' | 'baze';
  text: string;
  shots: Shot[];
  askPreset: boolean;
}

export interface BriefRow {
  label: string;
  value: string;
  swatch: string | null;
}

export interface BuildStep {
  id: string;
  label: string;
  state: 'done' | 'active' | 'waiting';
  progress: number;
}

export interface BuildView {
  kicker: string;
  title: string;
  subtitle: string;
  steps: BuildStep[];
  noticeTitle: string | null;
  noticeBody: string | null;
  waitingTitle: string;
  waitingBody: string;
}

export interface ReadyFact {
  label: string;
  value: string;
  swatch: string | null;
}

export interface SafetyCheck {
  id: string;
  tone: 'pass' | 'changed';
  text: string;
}

export interface ReadyView {
  kicker: string;
  title: string;
  address: string;
  color: string;
  icon: string;
  facts: ReadyFact[];
  openLabel: string;
  openPath: string;
  openHint: string;
  safetyTitle: string;
  checks: SafetyCheck[];
  publishLabel: string;
  shareLabel: string;
}

export interface Draft {
  id: string;
  kicker: string;
  messages: DraftMessage[];
  selectedPreset: PresetId;
  briefTitle: string;
  brief: BriefRow[];
  note: string;
  composerPlaceholder: string;
  makeLabel: string;
  build: BuildView;
  ready: ReadyView;
}

export interface WorkspaceBadge {
  label: string;
  tone: 'success' | 'warning' | 'muted';
}

export interface WorkspaceRow {
  id: string;
  cells: string[];
  badge: WorkspaceBadge | null;
  action: string | null;
}

export interface WorkspacePanel {
  title: string;
  stats: { label: string; value: string; note: string | null }[];
  columns: string[];
  rows: WorkspaceRow[];
  chartTitle: string;
  chartStart: string;
  chartEnd: string;
  bars: { height: number; current: boolean }[];
  empty: string | null;
}

export interface WorkspaceSection {
  id: string;
  label: string;
  panel: WorkspacePanel;
}

export interface Workspace {
  slug: string;
  name: string;
  preset: PresetId;
  color: string;
  icon: string;
  primaryAction: string;
  secondaryAction: string;
  sections: WorkspaceSection[];
  madeWithLabel: string;
  madeWithPath: string;
}
