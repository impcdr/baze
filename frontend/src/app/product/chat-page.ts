import { afterNextRender, ChangeDetectionStrategy, Component, viewChild } from '@angular/core';
import { ChatPanel } from '../chat/chat-panel';

@Component({
  selector: 'bz-chat-page',
  imports: [ChatPanel],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<app-chat-panel [docked]="false" />`,
  host: { class: 'flex min-h-0 flex-1 flex-col' },
})
export class ChatPage {
  private readonly panel = viewChild.required(ChatPanel);

  constructor() {
    afterNextRender(() => this.panel().focusComposer());
  }
}
