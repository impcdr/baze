import type { AppStep, AppTurn } from '../api/models';

export interface ChatEntry {
  kind: 'message' | 'steps';
  id: string;
  message?: AppTurn;
  steps?: AppStep[];
}

/** When the steps have no stored time, they belong just after the opening burst of messages. */
function appearedAt(messages: AppTurn[], steps: AppStep[]): number | null {
  const stamped = steps.find((step) => typeof step.createdAt === 'number')?.createdAt;
  if (typeof stamped === 'number') return stamped;
  if (messages.length === 0) return null;
  let burstEnd = messages[0].createdAt;
  for (let index = 1; index < messages.length; index += 1) {
    if (messages[index].createdAt - messages[index - 1].createdAt > 5000) break;
    burstEnd = messages[index].createdAt;
  }
  return burstEnd;
}

/** Build steps stay where they appeared. Later messages follow them. */
export function chatTimeline(messages: AppTurn[], steps: AppStep[]): ChatEntry[] {
  const at = appearedAt(messages, steps);
  const entries: ChatEntry[] = [];
  let placed = steps.length === 0;
  for (const message of messages) {
    if (!placed && at != null && message.createdAt > at) {
      entries.push({ kind: 'steps', id: 'build-steps', steps });
      placed = true;
    }
    entries.push({ kind: 'message', id: message.id, message });
  }
  if (!placed && steps.length) entries.push({ kind: 'steps', id: 'build-steps', steps });
  return entries;
}
