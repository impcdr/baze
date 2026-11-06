import { DestroyRef, Injectable, computed, effect, inject, signal } from '@angular/core';
import { replyFor } from './replies';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: number;
}

export interface Conversation {
  id: string;
  title: string;
  updatedAt: number;
  messages: ChatMessage[];
}

const STORAGE_KEY = 'kiln.v1';

interface Persisted {
  conversations: Conversation[];
  activeId: string | null;
}

@Injectable({ providedIn: 'root' })
export class ChatStore {
  private readonly destroyRef = inject(DestroyRef);
  private timer: ReturnType<typeof setTimeout> | null = null;

  readonly conversations = signal<Conversation[]>([]);
  readonly activeId = signal<string | null>(null);
  readonly streamingId = signal<string | null>(null);

  readonly active = computed(
    () => this.conversations().find((conversation) => conversation.id === this.activeId()) ?? null,
  );

  readonly messages = computed(() => this.active()?.messages ?? []);

  readonly streaming = computed(() => this.streamingId() !== null);

  constructor() {
    const saved = this.read();
    this.conversations.set(saved.conversations);
    this.activeId.set(saved.activeId);

    effect(() => {
      const payload: Persisted = {
        conversations: this.conversations(),
        activeId: this.activeId(),
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    });

    this.destroyRef.onDestroy(() => this.clearTimer());
  }

  select(id: string): void {
    this.activeId.set(id);
  }

  newChat(): void {
    this.stop();
    this.activeId.set(null);
  }

  send(text: string): void {
    const trimmed = text.trim();
    if (!trimmed || this.streaming()) {
      return;
    }

    const now = Date.now();
    const user: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      createdAt: now,
    };
    const assistant: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      createdAt: now + 1,
    };

    const current = this.conversations().find((conversation) => conversation.id === this.activeId());
    const conversationId = current?.id ?? crypto.randomUUID();

    if (!current) {
      const created: Conversation = {
        id: conversationId,
        title: titleFrom(trimmed),
        updatedAt: now,
        messages: [user, assistant],
      };
      this.conversations.update((list) => [created, ...list]);
      this.activeId.set(conversationId);
    } else {
      this.conversations.update((list) =>
        list.map((conversation) =>
          conversation.id === conversationId
            ? {
                ...conversation,
                title: conversation.messages.some((message) => message.role === 'user')
                  ? conversation.title
                  : titleFrom(trimmed),
                updatedAt: now,
                messages: [...conversation.messages, user, assistant],
              }
            : conversation,
        ),
      );
    }

    this.play(conversationId, assistant.id, replyFor(trimmed));
  }

  stop(): void {
    const id = this.streamingId();
    this.clearTimer();
    this.streamingId.set(null);
    if (!id) {
      return;
    }

    this.conversations.update((list) =>
      list
        .map((conversation) => ({
          ...conversation,
          messages: conversation.messages.flatMap((message) => {
            if (message.id !== id) {
              return [message];
            }
            return message.content ? [message] : [];
          }),
        }))
        .filter((conversation) => conversation.messages.length > 0),
    );

    if (!this.conversations().some((conversation) => conversation.id === this.activeId())) {
      this.activeId.set(this.conversations()[0]?.id ?? null);
    }
  }

  rename(id: string, title: string): void {
    const next = title.trim();
    if (!next) {
      return;
    }
    this.conversations.update((list) =>
      list.map((conversation) => (conversation.id === id ? { ...conversation, title: next } : conversation)),
    );
  }

  remove(id: string): void {
    const streamingHere = this.conversations()
      .find((conversation) => conversation.id === id)
      ?.messages.some((message) => message.id === this.streamingId());
    if (streamingHere) {
      this.stop();
    }
    this.conversations.update((list) => list.filter((conversation) => conversation.id !== id));
    if (this.activeId() === id) {
      this.activeId.set(this.conversations()[0]?.id ?? null);
    }
  }

  private play(conversationId: string, messageId: string, full: string): void {
    this.streamingId.set(messageId);
    let index = 0;

    const step = () => {
      index = Math.min(full.length, index + 24);
      const slice = full.slice(0, index);
      this.conversations.update((list) =>
        list.map((conversation) =>
          conversation.id === conversationId
            ? {
                ...conversation,
                messages: conversation.messages.map((message) =>
                  message.id === messageId ? { ...message, content: slice } : message,
                ),
              }
            : conversation,
        ),
      );
      if (index < full.length && this.streamingId() === messageId) {
        this.timer = setTimeout(step, 12);
      } else if (this.streamingId() === messageId) {
        this.streamingId.set(null);
        this.timer = null;
      }
    };

    this.timer = setTimeout(step, 12);
  }

  private clearTimer(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private read(): Persisted {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return { conversations: [], activeId: null };
      }
      const parsed = JSON.parse(raw) as Partial<Persisted>;
      const conversations = Array.isArray(parsed.conversations) ? parsed.conversations : [];
      const activeId = conversations.some((conversation) => conversation.id === parsed.activeId)
        ? (parsed.activeId ?? null)
        : null;
      return { conversations, activeId };
    } catch {
      return { conversations: [], activeId: null };
    }
  }
}

function titleFrom(text: string): string {
  const compact = text.replace(/\s+/g, ' ').trim();
  return compact.length > 42 ? `${compact.slice(0, 42).trimEnd()}…` : compact;
}
