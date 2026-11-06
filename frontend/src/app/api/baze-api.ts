import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Account, Draft, HomePayload, Preset, ShelfPayload, Workspace } from './models';

@Injectable({ providedIn: 'root' })
export class BazeApi {
  private readonly http = inject(HttpClient);

  account() {
    return this.http.get<Account>('/api/account');
  }

  home() {
    return this.http.get<HomePayload>('/api/home');
  }

  presets() {
    return this.http.get<Preset[]>('/api/presets');
  }

  apps(status = 'all') {
    const params = new HttpParams().set('status', status);
    return this.http.get<ShelfPayload>('/api/apps', { params });
  }

  shared() {
    return this.http.get<ShelfPayload>('/api/shared');
  }

  draft(id: string) {
    return this.http.get<Draft>(`/api/drafts/${id}`);
  }

  createDraft(prompt: string) {
    return this.http.post<Draft>('/api/drafts', { prompt });
  }

  choosePreset(id: string, preset: string) {
    return this.http.patch<Draft>(`/api/drafts/${id}`, { preset });
  }

  sendMessage(id: string, text: string) {
    return this.http.post<Draft>(`/api/drafts/${id}/messages`, { text });
  }

  publish(id: string) {
    return this.http.post<Draft>(`/api/drafts/${id}/publish`, {});
  }

  shareSafety(id: string) {
    return this.http.post<{ message: string }>(`/api/drafts/${id}/share`, {});
  }

  workspace(slug: string) {
    return this.http.get<Workspace>(`/api/apps/${slug}/workspace`);
  }
}
