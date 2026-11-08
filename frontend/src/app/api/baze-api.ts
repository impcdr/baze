import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Account, AppManage, AppStep, CreatorThread, Draft, HomePayload, Preset, ShelfApp, ShelfPayload, Workspace } from './models';

@Injectable({ providedIn: 'root' })
export class BazeApi {
  private readonly http = inject(HttpClient);

  account() {
    return this.http.get<Account>('/api/account');
  }

  useAccount(email: string) {
    return this.http.post<Account>('/api/account', { email });
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

  creator() {
    return this.http.get<CreatorThread>('/api/creator');
  }

  creatorMessage(content: string) {
    return this.http.post<CreatorThread>('/api/creator/messages', { content });
  }

  resetCreator() {
    return this.http.post<CreatorThread>('/api/creator/reset', {});
  }

  makeCreator(profile?: string) {
    return this.http.post<{ id: string; steps: AppStep[] }>('/api/creator/make', profile ? { profile } : {});
  }

  build(id: string) {
    return this.http.post<{ id: string }>(`/api/apps/${id}/build`, {});
  }

  deleteApp(id: string, code: string) {
    return this.http.delete(`/api/apps/${id}`, { body: { code }, responseType: 'text' });
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

  power(id: string, action: 'start' | 'stop') {
    return this.http.post<ShelfApp>(`/api/apps/${id}/power/${action}`, {});
  }

  manage(id: string) {
    return this.http.get<AppManage>(`/api/apps/${id}/manage`);
  }

  share(id: string, email: string, shared: boolean) {
    return this.http.post<{ shares: AppManage['shares'] }>(`/api/apps/${id}/share`, { email, shared });
  }

  persist(id: string, code: string) {
    return this.http.post<{ demo: boolean; expiresAt: number | null }>(`/api/apps/${id}/persist`, { code });
  }

  prompt(id: string, content: string, attachments: string[] = [], to?: 'supervisor') {
    return this.http.post<{ reply: string }>(`/api/apps/${id}/prompt`, { content, attachments, ...(to ? { to } : {}) });
  }

  approve(id: string, hosts: string[]) {
    return this.http.post<{ reply: string }>(`/api/apps/${id}/decisions`, { hosts });
  }

  allowBox(id: string, allow: boolean) {
    return this.http.post<{ reply: string }>(`/api/apps/${id}/decisions`, { allow });
  }

  leaveSecret(id: string, name: string, value: string) {
    return this.http.post<{ secrets: AppManage['secrets'] }>(`/api/apps/${id}/secrets`, { name, value });
  }

  readSecret(id: string, secretId: string) {
    return this.http.post<{ name: string; value: string; secrets: AppManage['secrets'] }>(
      `/api/apps/${id}/secrets/${secretId}`,
      {},
    );
  }

  upload(id: string, files: File[]) {
    const body = new FormData();
    for (const file of files) body.append('file', file, file.name);
    return this.http.post<{ files: { name: string; path: string }[] }>(`/api/apps/${id}/files`, body);
  }
}
