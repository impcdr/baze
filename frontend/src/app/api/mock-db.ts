import { HttpErrorResponse, HttpRequest, HttpResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, of, throwError } from 'rxjs';
import {
  ACCOUNT,
  FEATURED_IDS,
  HOME_COPY,
  PRESETS,
  PROMPT_DRAFTS,
  SHARED_APPS,
  SUGGESTIONS,
  WORKSPACES,
  YOUR_APPS,
  shiftsDraft,
  studioDraft,
} from './mock-data';
import type { Draft, PresetId, ShelfApp, ShelfPayload, Workspace, WorkspacePanel } from './models';

@Injectable({ providedIn: 'root' })
export class MockDb {
  private readonly apps: ShelfApp[] = structuredClone(YOUR_APPS);
  private readonly shared: ShelfApp[] = structuredClone(SHARED_APPS);
  private readonly drafts = new Map<string, Draft>([
    ['studio', studioDraft()],
    ['shifts', shiftsDraft()],
  ]);

  constructor() {
    const saved = this.read();
    if (!saved) return;
    this.apps.splice(0, this.apps.length, ...this.withCatalogCopy(saved.apps, YOUR_APPS));
    this.shared.splice(0, this.shared.length, ...this.withCatalogCopy(saved.shared, SHARED_APPS));
    this.drafts.clear();
    for (const draft of saved.drafts) this.drafts.set(draft.id, draft);
  }

  handle(req: HttpRequest<unknown>): Observable<HttpResponse<unknown>> {
    const url = new URL(req.url, 'http://baze.local');
    const parts = url.pathname.split('/').filter(Boolean);
    const method = req.method.toUpperCase();

    if (parts[0] !== 'api') {
      return throwError(() => new HttpErrorResponse({ status: 404, statusText: 'Not found' }));
    }

    const body = this.route(method, parts.slice(1), url, req);
    if (body === undefined) {
      return throwError(() => new HttpErrorResponse({ status: 404, statusText: 'Not found' }));
    }
    return of(new HttpResponse({ status: 200, body }));
  }

  private route(method: string, parts: string[], url: URL, req: HttpRequest<unknown>): unknown {
    const [first, second, third] = parts;
    const body = req.body;
    const status = req.params.get('status') || url.searchParams.get('status');

    if (method === 'GET' && first === 'account' && !second) return ACCOUNT;
    if (method === 'GET' && first === 'presets' && !second) return PRESETS;
    if (method === 'GET' && first === 'home' && !second) return this.home();
    if (method === 'GET' && first === 'apps' && !second) return this.shelf(status);
    if (method === 'GET' && first === 'shared' && !second) return this.sharedShelf();
    if (method === 'GET' && first === 'apps' && second && third === 'workspace') return this.workspace(second);
    if (method === 'POST' && first === 'drafts' && !second) return this.createDraft(body);
    if (method === 'GET' && first === 'drafts' && second && !third) return this.drafts.get(second);
    if (method === 'PATCH' && first === 'drafts' && second && !third) return this.choosePreset(second, body);
    if (method === 'POST' && first === 'drafts' && third === 'messages') return this.sendMessage(second, body);
    if (method === 'POST' && first === 'drafts' && third === 'publish') return this.publish(second);
    if (method === 'POST' && first === 'drafts' && third === 'share') return this.share(second);
    return undefined;
  }

  private home() {
    const featured = FEATURED_IDS.map((id) => this.apps.find((app) => app.id === id)).filter((app) => !!app);
    return {
      ...HOME_COPY,
      seeAllLabel: `See all ${this.apps.length}`,
      suggestions: SUGGESTIONS,
      featured,
    };
  }

  private shelf(status: string | null): ShelfPayload {
    const live = this.apps.filter((app) => app.status === 'live').length;
    const match = (app: ShelfApp) => !status || status === 'all' || app.status === status;
    return {
      title: 'My apps',
      summary: `${this.apps.length} apps on your shelf · ${live} live`,
      makeLabel: 'Make an app',
      filters: [
        { id: 'all', label: 'All' },
        { id: 'live', label: 'Live' },
        { id: 'building', label: 'Being made' },
      ],
      empty: 'Nothing on the shelf matches that.',
      apps: this.apps.filter(match),
      sharedTitle: 'Shared with me',
      sharedSummary: `${this.shared.length} apps people shared with you`,
      shared: this.shared.filter(match),
    };
  }

  private sharedShelf(): ShelfPayload {
    const page = this.shelf('all');
    return {
      ...page,
      title: page.sharedTitle,
      summary: page.sharedSummary,
      filters: [],
      empty: 'Nothing has been shared with you yet.',
      apps: page.shared,
    };
  }

  private workspace(slug: string): Workspace | undefined {
    const known = WORKSPACES[slug];
    if (known) {
      const copy = structuredClone(known);
      const app = this.apps.find((item) => item.slug === slug);
      if (app) {
        copy.preset = app.preset;
        copy.color = app.color;
      }
      return copy;
    }
    const app = [...this.apps, ...this.shared].find((item) => item.slug === slug);
    if (!app) return undefined;
    return this.plainWorkspace(app);
  }

  private plainWorkspace(app: ShelfApp): Workspace {
    const panel: WorkspacePanel = {
      title: app.name,
      empty: app.summary,
      stats: [],
      columns: [],
      rows: [],
      chartTitle: '',
      chartStart: '',
      chartEnd: '',
      bars: [],
    };
    return {
      slug: app.slug,
      name: app.name,
      preset: app.preset,
      color: app.color,
      icon: app.icon,
      primaryAction: 'Open',
      secondaryAction: 'Export',
      madeWithLabel: 'Made with baze',
      madeWithPath: '/',
      sections: [{ id: 'home', label: 'Home', panel }],
    };
  }

  private createDraft(body: unknown): Draft {
    const prompt = typeof body === 'object' && body && 'prompt' in body ? String((body as { prompt: string }).prompt) : '';
    const text = prompt.toLowerCase();
    const hit = PROMPT_DRAFTS.find((item) => text.includes(item.match));
    if (hit) {
      const existing = this.drafts.get(hit.id);
      if (existing) return existing;
    }
    const draft = this.blankDraft(prompt.trim() || 'Something new for the shelf');
    this.drafts.set(draft.id, draft);
    this.save();
    return draft;
  }

  private blankDraft(prompt: string): Draft {
    const preset = PRESETS[0];
    const id = `draft-${this.drafts.size + 1}`;
    const name = prompt.split('.')[0].slice(0, 42);
    return {
      id,
      kicker: 'Step 1 of 3 · Describe',
      selectedPreset: preset.id,
      briefTitle: 'What I’m making',
      composerPlaceholder: 'Tell me what to change…',
      makeLabel: 'Looks right, make it',
      note: 'You’ll see screenshots here while we shape it. Once it’s made, your app opens in its own browser tab.',
      brief: [
        { label: 'Name', value: name, swatch: null },
        { label: 'Its one job', value: 'One job, decided in the chat', swatch: null },
        { label: 'Look', value: preset.label, swatch: preset.color },
        { label: 'Talks to', value: 'Your email only', swatch: null },
      ],
      messages: [
        { id: `${id}-you`, role: 'you', text: prompt, shots: [], askPreset: false },
        {
          id: `${id}-baze`,
          role: 'baze',
          text: `Here’s a first look. ${name} stays one job, and we’ll shape the views in this chat.`,
          shots: [{ id: 'first', name: 'First view', accent: preset.color }],
          askPreset: true,
        },
      ],
      build: {
        kicker: 'Step 2 of 3 · Making it',
        title: `${name} is taking shape`,
        subtitle: 'About a minute left. You can close this page, we’ll email you when it’s ready.',
        steps: [
          { id: 'write', label: 'Writing it', state: 'done', progress: 100 },
          { id: 'try', label: 'Trying it safely', state: 'active', progress: 40 },
          { id: 'check', label: 'Checking it’s safe', state: 'waiting', progress: 0 },
          { id: 'ready', label: 'Ready for you', state: 'waiting', progress: 0 },
        ],
        noticeTitle: null,
        noticeBody: null,
        waitingTitle: 'While you wait',
        waitingBody: 'We’re trying it inside a sealed space that can only reach your email.',
      },
      ready: {
        kicker: 'Step 3 of 3 · Ready',
        title: `${name} is ready`,
        address: `baze.app/${id} · ${preset.label} look`,
        color: preset.color,
        icon: 'lucideReceipt',
        facts: [
          { label: 'Its one job', value: 'One job, decided in the chat', swatch: null },
          { label: 'Look', value: preset.label, swatch: preset.color },
          { label: 'Talks to', value: 'Your email only', swatch: null },
        ],
        openLabel: 'Open your app',
        openPath: '/',
        openHint: 'It opens in its own browser tab. Baze stays here.',
        safetyTitle: 'Safety check',
        checks: [
          { id: 'works', tone: 'pass', text: 'It works. We tried the one job inside the safe space.' },
          { id: 'email', tone: 'pass', text: 'It only talks to your email.' },
        ],
        publishLabel: 'Put it live',
        shareLabel: 'Share the safety check',
      },
    };
  }

  private choosePreset(id: string, body: unknown): Draft | undefined {
    const draft = this.drafts.get(id);
    if (!draft) return undefined;
    const presetId = typeof body === 'object' && body && 'preset' in body ? String((body as { preset: string }).preset) : '';
    const preset = PRESETS.find((item) => item.id === presetId);
    if (!preset) return draft;
    draft.selectedPreset = preset.id as PresetId;
    draft.brief = draft.brief.map((row) => (row.label === 'Look' ? { ...row, value: preset.label, swatch: preset.color } : row));
    draft.ready = {
      ...draft.ready,
      color: preset.color,
      address: draft.ready.address.replace(/·.*/, `· ${preset.label} look`),
      facts: draft.ready.facts.map((row) => (row.label === 'Look' ? { ...row, value: preset.label, swatch: preset.color } : row)),
    };
    for (const message of draft.messages) {
      message.shots = message.shots.map((shot) => ({ ...shot, accent: preset.color }));
    }
    const app = this.apps.find((item) => item.id === id);
    if (app) {
      app.preset = preset.id;
      app.color = preset.color;
    }
    this.save();
    return draft;
  }

  private sendMessage(id: string, body: unknown): Draft | undefined {
    const draft = this.drafts.get(id);
    if (!draft) return undefined;
    const text = typeof body === 'object' && body && 'text' in body ? String((body as { text: string }).text).trim() : '';
    if (!text) return draft;
    draft.messages = [
      ...draft.messages,
      { id: `${id}-${draft.messages.length + 1}`, role: 'you', text, shots: [], askPreset: false },
      {
        id: `${id}-${draft.messages.length + 2}`,
        role: 'baze',
        text: 'Noted. I’ll keep that in the app, and the screenshots stay the ones you can see.',
        shots: [],
        askPreset: false,
      },
    ];
    this.save();
    return draft;
  }

  private publish(id: string): Draft | undefined {
    const draft = this.drafts.get(id);
    if (!draft) return undefined;
    const app = this.apps.find((item) => item.id === id);
    if (app) {
      app.status = 'live';
      app.statusLabel = 'Live';
      app.progress = null;
      app.badge = 'New';
      app.isNew = true;
      app.labels = [
        { text: 'New', tone: 'secondary' },
        { text: 'Live', tone: 'success' },
      ];
      if (app.slug) {
        app.path = `/a/${app.slug}`;
        app.external = true;
      }
    }
    this.save();
    return draft;
  }

  private share(id: string): { message: string } | undefined {
    const draft = this.drafts.get(id);
    if (!draft) return undefined;
    return { message: 'The safety check link is ready to share.' };
  }

  private save(): void {
    if (typeof localStorage === 'undefined') return;
    const payload = {
      apps: this.apps,
      shared: this.shared,
      drafts: [...this.drafts.values()],
    };
    localStorage.setItem('baze.mock.v1', JSON.stringify(payload));
  }

  /** Seeded apps keep the catalog description. Status and look stay as saved. */
  private withCatalogCopy(saved: ShelfApp[], catalog: ShelfApp[]): ShelfApp[] {
    const copy = new Map(catalog.map((app) => [app.id, app]));
    return saved.map((app) => {
      const fresh = copy.get(app.id);
      if (!fresh) return app;
      const labels = app.status === fresh.status && app.badge === fresh.badge ? fresh.labels : app.labels;
      return { ...app, summary: fresh.summary, detail: fresh.detail, labels };
    });
  }

  private read(): { apps: ShelfApp[]; shared: ShelfApp[]; drafts: Draft[] } | null {
    if (typeof localStorage === 'undefined') return null;
    const raw = localStorage.getItem('baze.mock.v1');
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as { apps?: ShelfApp[]; shared?: ShelfApp[]; drafts?: Draft[] };
      if (!Array.isArray(parsed.apps) || !Array.isArray(parsed.shared) || !Array.isArray(parsed.drafts)) return null;
      return { apps: parsed.apps, shared: parsed.shared, drafts: parsed.drafts };
    } catch {
      return null;
    }
  }
}
