const REPLIES: { test: (text: string) => boolean; body: string }[] = [
  {
    test: (text) => text.includes('rewrite') || text.includes('clear'),
    body: 'A clearer version:\n\nSay the point in one sentence. Then the reason. Then what you want the reader to do.\n\nCut any sentence that repeats the one before it. If you paste the original, I can tighten it line by line.',
  },
  {
    test: (text) => text.includes('weekend'),
    body: 'A quiet weekend, kept small:\n\nSaturday morning — a long walk before the town wakes up.\nSaturday afternoon — one good meal, cooked slowly.\nSunday — nothing scheduled past noon.\n\nLeave one evening empty on purpose.',
  },
  {
    test: (text) => text.includes('signal'),
    body: 'Signals are values Angular can watch. You read one by calling it, and the view updates when it changes.\n\nA computed signal derives from other signals. An effect runs when the signals it reads change — useful at the edges, easy to overuse.\n\nPrefer computed for anything you show. Keep effects for persistence and other side effects.',
  },
  {
    test: (text) => text.includes('note') || text.includes('draft'),
    body: 'A short note:\n\nThanks for the time today. I will send the next version by Friday, and I will flag anything that needs a decision before then.',
  },
];

export function replyFor(prompt: string): string {
  const text = prompt.toLowerCase();
  const match = REPLIES.find((entry) => entry.test(text));
  if (match) {
    return match.body;
  }
  const subject = prompt.trim().replace(/\s+/g, ' ');
  return `Here is a careful take.\n\nYou asked: “${subject}”\n\nStart with the outcome you want, then the constraint that matters most, then the first small step. Tell me which of those is still fuzzy and we can sharpen it.`;
}
