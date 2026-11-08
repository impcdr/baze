export type AppStatus = 'live' | 'stopped' | 'building' | 'attention' | 'paused' | 'error' | 'closed';
export type PresetId = 'ocean' | 'forest' | 'sunset' | 'plum' | 'graphite' | 'rose';
export type AppLabelTone = 'default' | 'secondary' | 'success' | 'warning' | 'outline';

export interface AppLabel {
  text: string;
  tone: AppLabelTone;
}

export interface AccountPerson {
  name: string;
  email: string;
  initials: string;
  color: string;
  ink: string;
}

export interface Account {
  name: string;
  initials: string;
  color: string;
  ink: string;
  email: string;
  studio: string;
  accounts: AccountPerson[];
}

export interface AppShareRow {
  name: string;
  email: string;
  initials: string;
  color: string;
  ink: string;
  owner: boolean;
  shared: boolean;
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
  people: AccountPerson[];
  runnable: boolean;
  deletable: boolean;
  statusError: string | null;
  demo: boolean;
  sealed: boolean;
  expiresAt: number | null;
}

export interface AppTurn {
  id: string;
  role: 'user' | 'assistant' | 'progress' | 'supervisor';
  content: string;
  createdAt: number;
  state?: 'waiting' | 'active' | 'done' | 'stopped';
  stepId?: string;
  decided?: boolean;
  decision?: string;
}

export interface FlowNode {
  id: string;
  label: string;
  kind: 'person' | 'page' | 'store' | 'file' | 'outside';
}

export interface FlowEdge {
  from: string;
  to: string;
}

export interface ChartEntry {
  id: string;
  kind: 'created' | 'changed' | 'containment' | 'decision';
  summary: string;
  detail?: string;
  at: number;
}

export interface AppManage {
  id: string;
  name: string;
  summary: string;
  status: AppStatus;
  statusLabel: string;
  createdAt: number | null;
  lastRunAt: number | null;
  path: string | null;
  color: string;
  icon: string;
  runnable: boolean;
  deletable: boolean;
  statusError: string | null;
  boxReady: boolean;
  working: boolean;
  activity: string;
  steps: AppStep[];
  messages: AppTurn[];
  flow: { nodes: FlowNode[]; edges: FlowEdge[] };
  record: ChartEntry[];
  actions: { id: string; label: string }[];
  sites: { host: string; suggested: boolean }[];
  request: { host: string; why: string }[];
  allowed: string[];
  closed: string[];
  canPrompt: boolean;
  sealed: boolean;
  sharedBy: string | null;
  shares: AppShareRow[];
  demo: boolean;
  expiresAt: number | null;
  box: BoxChoice | null;
  boxPrompt: string | null;
  check: boolean;
  files?: GivenFile[];
  secrets: AppSecrets | null;
}

export interface AppSecrets {
  forYou: SecretNote[];
  forApp: SecretNote[];
  log: SecretLog[];
}

export interface SecretNote {
  id: string;
  name: string;
  at: number;
}

export interface SecretLog {
  id: string;
  name: string;
  to: 'agent' | 'user';
  event: 'left' | 'read';
  at: number;
}

export interface GivenFile {
  name: string;
  size: number;
  where: 'specimen' | 'uploads' | 'record' | string;
}

export interface AppStep {
  id: string;
  label: string;
  state: 'waiting' | 'active' | 'done';
  createdAt?: number | null;
}

export interface AppSketch {
  name: string;
  summary: string;
  icon: string;
  color: string;
}

export interface BoxChoice {
  id: 'web' | 'data' | 'quarantine' | string;
  name: string;
  sentence: string;
}

export interface CreatorThread {
  messages: AppTurn[];
  sketch: AppSketch;
  boxes: BoxChoice[];
  recommended: string;
  reason: string;
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

export interface ShelfCheck {
  id: string;
  name: string;
  specimen: string;
  verdict: 'clear' | 'suspicious' | 'pending';
  report: string;
  reason: string;
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
  checks: ShelfCheck[];
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
