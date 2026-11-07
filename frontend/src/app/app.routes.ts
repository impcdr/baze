import { Routes, UrlMatchResult, UrlSegment } from '@angular/router';
import { BuildingPage } from './product/building-page';
import { ChatPage } from './product/chat-page';
import { HomePage } from './product/home-page';
import { MakePage } from './product/make-page';
import { OpenAppPage } from './product/open-app-page';
import { ReadyPage } from './product/ready-page';
import { ShelfPage } from './product/shelf-page';
import { Shell } from './product/shell';

/** Live apps are served at /<32-character hex id>. */
export function appIdMatcher(segments: UrlSegment[]): UrlMatchResult | null {
  if (segments.length !== 1 || !/^[0-9a-f]{32}$/.test(segments[0].path)) return null;
  return { consumed: segments, posParams: { appId: segments[0] } };
}

export const routes: Routes = [
  { matcher: appIdMatcher, component: OpenAppPage },
  {
    path: '',
    component: Shell,
    children: [
      { path: '', pathMatch: 'full', component: HomePage, title: 'Baze' },
      { path: 'apps', component: ShelfPage, title: 'My apps' },
      { path: 'chat', component: ChatPage, title: 'Chat' },
      { path: 'shared', redirectTo: '/apps', pathMatch: 'full' },
      { path: 'make/:id', component: MakePage, title: 'Describe' },
      { path: 'building/:id', component: BuildingPage, title: 'Making it' },
      { path: 'ready/:id', component: ReadyPage, title: 'Ready' },
    ],
  },
];
