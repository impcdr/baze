import type { Conversation } from './chat-store';

const started = Date.UTC(2026, 10, 5, 16, 0, 0);

function message(id: string, role: 'user' | 'assistant', content: string, minute: number) {
  return { id, role, content, createdAt: started + minute * 60_000 };
}

/** First-visit thread. Shown only when this browser has no saved chat yet. */
export function seededChat(): Conversation {
  return {
    id: 'seed-studio-invoices',
    title: 'Studio invoices',
    updatedAt: started + 24 * 60_000,
    messages: [
      message(
        'seed-1',
        'user',
        'I want something for studio invoices. People forget to pay, and I end up writing the same email every week.',
        0,
      ),
      message(
        'seed-2',
        'assistant',
        'Keep it to one job: show what is still unpaid, and send a reminder.\n\nThe first screen is a single list. Each row is the client, the invoice, and how late it is. The only action on the row is Send reminder.\n\nLeave out totals, charts, and a settings page. When a client has paid, the row leaves the list.',
        2,
      ),
      message(
        'seed-3',
        'user',
        'The reminder has to sound like me, not like a bank.',
        6,
      ),
      message(
        'seed-4',
        'assistant',
        'Here is a first draft you can send as it is.\n\nHi Mara,\n\nThis is a short reminder that invoice 1042 is still open. If it has already gone through, you can ignore this note.\n\nThank you,\nLena\n\nThe app keeps that wording. You change it by asking, the same way you would change a sentence here.',
        8,
      ),
      message(
        'seed-5',
        'user',
        'What if two invoices are late for the same client? I do not want two emails.',
        12,
      ),
      message(
        'seed-6',
        'assistant',
        'Group them. One row per client, and the reminder names every open invoice in that one note.\n\nThe row shows the oldest due date, so the person who has waited longest stays at the top. Sending once clears the reminder for that client, not for the whole list.',
        14,
      ),
      message('seed-7', 'user', 'And when everyone has paid?', 18),
      message(
        'seed-8',
        'assistant',
        'The list is empty, and the page says one line:\n\nNothing is waiting. New invoices will show up here.\n\nNo illustration and no extra button. The next invoice is what brings the list back.',
        20,
      ),
      message('seed-9', 'user', 'Where does a new invoice come from?', 23),
      message(
        'seed-10',
        'assistant',
        'From the same list. A quiet Add invoice sits at the end of the page, not in a second destination.\n\nIt asks for the client, the amount, and a due date. That is the whole form. After you save, the row appears in the list, and the reminder uses the wording you already set.',
        24,
      ),
    ],
  };
}
