import { Routes } from '@angular/router';
import { BuildingPage } from './product/building-page';
import { ChatPage } from './product/chat-page';
import { HomePage } from './product/home-page';
import { MakePage } from './product/make-page';
import { OpenAppPage } from './product/open-app-page';
import { ReadyPage } from './product/ready-page';
import { ShelfPage } from './product/shelf-page';
import { Shell } from './product/shell';

export const routes: Routes = [
  { path: 'a/:slug', component: OpenAppPage },
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
