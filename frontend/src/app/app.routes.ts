import { Routes } from '@angular/router';
import { BuildingPage } from './product/building-page';
import { CreatorPage } from './product/creator-page';
import { HomePage } from './product/home-page';
import { MakePage } from './product/make-page';
import { ManagePage } from './product/manage-page';
import { QuarantinePage } from './product/quarantine-page';
import { ReadyPage } from './product/ready-page';
import { ShelfPage } from './product/shelf-page';
import { Shell } from './product/shell';

export const routes: Routes = [
  {
    path: '',
    component: Shell,
    children: [
      { path: '', pathMatch: 'full', component: HomePage, title: 'Baze' },
      { path: 'apps', component: ShelfPage, title: 'Apps' },
      { path: 'verify', component: QuarantinePage, title: 'Verify' },
      { path: 'verify/:id', component: ManagePage, title: 'Verify' },
      { path: 'quarantine', redirectTo: 'verify', pathMatch: 'full' },
      { path: 'apps/:id', component: ManagePage, title: 'Manage app' },
      { path: 'creator', component: CreatorPage, title: 'Creator' },
      { path: 'chat', redirectTo: 'apps', pathMatch: 'full' },
      { path: 'shared', redirectTo: '/apps', pathMatch: 'full' },
      { path: 'make/:id', component: MakePage, title: 'Describe' },
      { path: 'building/:id', component: BuildingPage, title: 'Making it' },
      { path: 'ready/:id', component: ReadyPage, title: 'Ready' },
    ],
  },
];
